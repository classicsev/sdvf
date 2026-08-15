"""
Учёт как identity-провайдер для СДВФ — единый вход: пользователь логинится
в Учёте (email/пароль или уже подключённые VK ID/Яндекс ID/Sber ID), и тем же
аккаунтом попадает в СДВФ, без отдельной регистрации там.

В отличие от routers/oauth.py (где Учёт ПОТРЕБЛЯЕТ чужой OAuth), здесь Учёт
сам выступает провайдером для одного доверенного клиента (СДВФ) — упрощённый
authorization code flow без полноценного реестра OAuth-клиентов (он не нужен
ради единственного потребителя) и без выдачи СДВФ настоящего JWT Учёта: СДВФ
получает только личность (email/имя), не доступ к API Учёта.

Поток при purpose=login (вход):
  1. СДВФ редиректит браузер на GET /oauth/authorize?redirect_uri=...&state=...
  2. Бэкенд проверяет redirect_uri по строгому allowlist и редиректит на
     фронтенд Учёта — экран входа/согласия.
  3. Фронтенд (уже зная JWT пользователя из своего localStorage/контекста)
     вызывает POST /oauth/consent — авторизованный запрос, возвращает
     redirect_url с одноразовым короткоживущим code.
  4. Браузер переходит по redirect_url на колбэк СДВФ.
  5. СДВФ сервер-ту-сервер обменивает code на личность через POST /oauth/token
     (с client_secret — это уже не браузерный запрос, секрет не палится).

Поток при purpose=link (привязка существующего аккаунта СДВФ к аккаунту Учёта):
  Шаги 1-2 те же самые. Дальше иначе — простого клика в уже открытой сессии
  браузера недостаточно (сессия могла остаться от другого человека на том же
  устройстве, а привязка аккаунта — чувствительное действие, не обычный вход):
  3. POST /oauth/consent с purpose=link НЕ выдаёт code сразу, а отправляет
     письмо на email пользователя (реальный, уже подтверждённый — Учёт умеет
     слать почту, в отличие от СДВФ) со ссылкой на GET /oauth/link-confirm.
  4. Только переход по ссылке ИЗ ПИСЬМА (доказывает владение почтой, а не
     просто активную сессию в браузере) выдаёт code и редиректит на колбэк
     СДВФ — дальше тот же обмен через POST /oauth/token, что и при входе.
"""
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.auth import (
    create_sso_identity_code,
    create_sso_link_confirm_token,
    decode_sso_identity_code,
    decode_sso_link_confirm_token,
    get_current_user,
)
from app.config import settings
from app.database import get_db
from app.mailer import send_sso_link_confirmation_email
from app.models import User
from sqlalchemy.orm import Session

router = APIRouter(prefix="/oauth", tags=["identity-provider"])


def _sso_configured() -> bool:
    return bool(settings.sdvf_sso_redirect_uri and settings.sdvf_sso_client_secret)


def _allowed_redirect_uris() -> set[str]:
    # Реестр доверенных клиентов — ровно два колбэка одного и того же партнёра
    # (СДВФ): вход и привязка аккаунта. Пустые значения (не настроено) не
    # попадают в набор, чтобы пустая строка redirect_uri не проходила валидацию.
    return {uri for uri in (settings.sdvf_sso_redirect_uri, settings.sdvf_sso_link_redirect_uri) if uri}


def _validate_redirect_uri(redirect_uri: str) -> None:
    if not _sso_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SSO не настроен")
    if redirect_uri not in _allowed_redirect_uris():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый redirect_uri")


@router.get("/authorize")
def authorize(redirect_uri: str = Query(...), state: str = Query(...), purpose: str = Query("login")):
    _validate_redirect_uri(redirect_uri)
    # purpose — только для текста экрана согласия на фронте (login/link), на
    # выдачу кода не влияет: что делать с личностью после колбэка, решает СДВФ.
    query = urlencode({"redirect_uri": redirect_uri, "state": state, "client": "sdvf", "purpose": purpose})
    return RedirectResponse(f"{settings.frontend_base_url}/sso-consent?{query}")


class ConsentIn(BaseModel):
    redirect_uri: str
    state: str
    purpose: str = "login"


class ConsentOut(BaseModel):
    # Ровно одно из двух заполнено: redirect_url — код уже выдан, переходим
    # сразу (purpose=login); email_sent_to — код придёт по ссылке в письме
    # (purpose=link), фронт показывает "проверьте почту" вместо редиректа.
    redirect_url: Optional[str] = None
    email_sent_to: Optional[str] = None


@router.post("/consent", response_model=ConsentOut)
def consent(payload: ConsentIn, user: User = Depends(get_current_user)):
    """Вызывается фронтендом Учёта (авторизованный запрос — get_current_user
    подтверждает, что пользователь реально залогинен и это не подделанный
    запрос) после того, как человек нажал "Продолжить" на экране согласия."""
    _validate_redirect_uri(payload.redirect_uri)

    if payload.purpose == "link":
        # Привязка аккаунта — чувствительнее обычного входа: активная сессия
        # в браузере сама по себе ничего не доказывает (см. модуль docstring),
        # поэтому code не выдаём сразу, а требуем подтверждения по почте.
        if not user.email or not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для привязки аккаунта нужен подтверждённый email — подтвердите его в профиле",
            )
        token = create_sso_link_confirm_token(user.id, payload.redirect_uri, payload.state)
        send_sso_link_confirmation_email(user.email, token, client_name="СДВФ")
        return ConsentOut(email_sent_to=user.email)

    code = create_sso_identity_code(user.id)
    query = urlencode({"code": code, "state": payload.state})
    return ConsentOut(redirect_url=f"{payload.redirect_uri}?{query}")


@router.get("/link-confirm")
def link_confirm(token: str = Query(...)):
    """Переход по ссылке из письма (см. consent(purpose=link)) — единственное
    реальное доказательство владения почтой в этой схеме. Без входа в Учёт:
    сама ссылка уже несёт подписанное разрешение на конкретного user_id."""
    payload = decode_sso_link_confirm_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ссылка недействительна или устарела")

    redirect_uri = payload["redirect_uri"]
    # Повторная проверка allowlist на случай, если он изменился между отправкой
    # письма и переходом по ссылке (ссылка живёт до 30 минут).
    _validate_redirect_uri(redirect_uri)

    code = create_sso_identity_code(payload["sub"])
    query = urlencode({"code": code, "state": payload["state"]})
    return RedirectResponse(f"{redirect_uri}?{query}")


class TokenIn(BaseModel):
    code: str
    client_secret: str


class TokenOut(BaseModel):
    user_id: str
    email: str | None
    full_name: str
    email_verified: bool


@router.post("/token", response_model=TokenOut)
def token(payload: TokenIn, db: Session = Depends(get_db)):
    if not _sso_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SSO не настроен")
    # compare_digest не используется намеренно здесь по единообразию с остальным
    # проектом (см. resend-verification и др.) — секрет сравнивается server-to-server,
    # не в браузерном запросе, риск timing-атаки практически отсутствует.
    if payload.client_secret != settings.sdvf_sso_client_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный client_secret")

    user_id = decode_sso_identity_code(payload.code)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Код недействителен или устарел")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь не найден")

    return TokenOut(user_id=user.id, email=user.email, full_name=user.full_name, email_verified=user.email_verified)
