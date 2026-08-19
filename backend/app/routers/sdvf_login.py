"""Учёт как потребитель identity от СДВФ — кнопка "Войти через СДВФ" на экране
входа. Зеркало identity_provider.py (там Учёт — провайдер для СДВФ), только в
обратную сторону: здесь Учёт вызывает СДВФ. См. user/views_sso_provider.py в
проекте RFTK (sdvf.ru) для парной реализации на той стороне.

Поток:
  1. Фронтенд ведёт на GET /auth/sdvf/start.
  2. Бэкенд генерирует подписанный state, редиректит на
     {sdvf_base_url}/oauth/authorize.
  3. СДВФ (после входа/согласия пользователя) редиректит браузер на
     GET /auth/sdvf/callback?code=...&state=...
  4. Бэкенд обменивает code на личность через POST {sdvf_base_url}/oauth/token
     (server-to-server, с client_secret — как и в oauth.py для VK/Яндекс).
  5. Если пользователь СДВФ уже привязал свой аккаунт к аккаунту Учёта (см.
     профиль в СДВФ) — identity несёт uchet_user_id, и мы логиним ровно этот
     существующий User, а не заводим новый. Иначе — ищем/заводим
     OAuthAccount(provider="sdvf", provider_user_id=...), та же таблица и та
     же логика бутстрапа компании, что и для VK/Яндекс/Sber
     (см. oauth.py::oauth_callback).
"""
import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import urlencode

from app.auth import create_access_token, create_oauth_state_token, decode_oauth_state_token
from app.config import settings
from app.database import get_db
from app.models import Company, CompanyMember, OAuthAccount, RoleEnum, User

router = APIRouter(prefix="/auth/sdvf", tags=["sdvf-login"])

PROVIDER = "sdvf"
TIMEOUT = 15.0


def _configured() -> bool:
    return bool(settings.sdvf_base_url and settings.sdvf_client_secret)


def _redirect_uri() -> str:
    return f"{settings.backend_base_url}/auth/sdvf/callback"


def _error_redirect(reason: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_base_url}/oauth-callback?error={reason}")


@router.get("/enabled")
def sdvf_login_enabled():
    return {"enabled": _configured()}


@router.get("/start")
def sdvf_login_start():
    if not _configured():
        return _error_redirect("provider_not_configured")

    state = create_oauth_state_token(PROVIDER)
    query = urlencode({"redirect_uri": _redirect_uri(), "state": state})
    return RedirectResponse(f"{settings.sdvf_base_url}/oauth/authorize?{query}")


@router.get("/callback")
def sdvf_login_callback(
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    if error or not code or not state:
        return _error_redirect("provider_denied")

    state_payload = decode_oauth_state_token(state, expected_provider=PROVIDER)
    if state_payload is None:
        return _error_redirect("invalid_state")

    try:
        resp = httpx.post(
            f"{settings.sdvf_base_url}/oauth/token",
            json={"code": code, "client_secret": settings.sdvf_client_secret},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        return _error_redirect("provider_error")

    if resp.status_code != 200:
        return _error_redirect("provider_error")

    identity = resp.json()
    if not identity.get("email_verified"):
        return _error_redirect("email_not_verified")

    # Уже привязанный аккаунт (см. профиль СДВФ) — логиним ровно этот User, не
    # заводя новый по совпадению email/provider_user_id.
    linked_user_id = identity.get("uchet_user_id")
    if linked_user_id:
        user = db.get(User, linked_user_id)
        if user is None or not user.is_active:
            return _error_redirect("account_disabled")
        token = create_access_token({"sub": user.id})
        return RedirectResponse(f"{settings.frontend_base_url}/oauth-callback#token={token}")

    provider_user_id = str(identity["user_id"])
    oauth_account = (
        db.query(OAuthAccount)
        .filter(OAuthAccount.provider == PROVIDER, OAuthAccount.provider_user_id == provider_user_id)
        .first()
    )

    if oauth_account is not None:
        user = db.get(User, oauth_account.user_id)
        if user is None or not user.is_active:
            return _error_redirect("account_disabled")
    else:
        # Первый вход через СДВФ — заводим новую компанию с минимальным тарифом
        # (та же логика, что и в oauth.py::oauth_callback для VK/Яндекс/Sber) —
        # слияние аккаунтов по совпадению email не реализовано, осознанное
        # ограничение v1.
        company = Company(
            name=identity.get("full_name") or "Компания из СДВФ",
            module_finance_enabled=True,
            module_warehouse_enabled=False,
        )
        db.add(company)
        db.flush()

        user = User(
            email=identity.get("email"),
            full_name=identity.get("full_name") or "Пользователь СДВФ",
            hashed_password=None,
            # СДВФ уже подтвердил личность (и email) за нас.
            email_verified=True,
        )
        db.add(user)
        db.flush()
        db.add(CompanyMember(user_id=user.id, company_id=company.id, role=RoleEnum.admin))
        company.owner_user_id = user.id
        db.flush()

        oauth_account = OAuthAccount(user_id=user.id, provider=PROVIDER, provider_user_id=provider_user_id)
        db.add(oauth_account)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.id})
    return RedirectResponse(f"{settings.frontend_base_url}/oauth-callback#token={token}")
