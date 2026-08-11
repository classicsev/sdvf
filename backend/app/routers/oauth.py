from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import create_access_token, create_oauth_state_token, decode_oauth_state_token
from app.config import settings
from app.database import get_db
from app.integrations import oauth_providers
from app.integrations.oauth_providers import OAuthError
from app.models import Company, CompanyMember, OAuthAccount, RoleEnum, User

router = APIRouter(prefix="/auth/oauth", tags=["oauth"])


def _redirect_uri(provider: str) -> str:
    return f"{settings.backend_base_url}/auth/oauth/{provider}/callback"


def _error_redirect(reason: str) -> RedirectResponse:
    # Ошибку показываем на фронте, а не голым 400 — пользователь в этот момент
    # уже ушёл с провайдера в браузере, ему некуда будет посмотреть на JSON-ответ.
    return RedirectResponse(f"{settings.frontend_base_url}/oauth-callback?error={reason}")


@router.get("/providers")
def list_providers():
    return {"providers": oauth_providers.list_configured_providers()}


@router.get("/{provider}/start")
def oauth_start(provider: str):
    if not oauth_providers.is_configured(provider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Провайдер не настроен")

    config = oauth_providers.get_provider(provider)
    code_verifier = None
    code_challenge = None
    if config.uses_pkce:
        code_verifier, code_challenge = oauth_providers.generate_pkce_pair()

    state = create_oauth_state_token(provider, code_verifier=code_verifier)
    url = oauth_providers.build_authorize_url(
        provider, redirect_uri=_redirect_uri(provider), state=state, code_challenge=code_challenge
    )
    return RedirectResponse(url)


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    device_id: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    if error or not code or not state:
        return _error_redirect("provider_denied")

    state_payload = decode_oauth_state_token(state, expected_provider=provider)
    if state_payload is None:
        return _error_redirect("invalid_state")

    try:
        token_data = oauth_providers.exchange_code(
            provider,
            code=code,
            redirect_uri=_redirect_uri(provider),
            code_verifier=state_payload.get("code_verifier"),
            device_id=device_id,
        )
        access_token = token_data.get("access_token")
        if not access_token:
            return _error_redirect("no_access_token")
        raw_profile = oauth_providers.fetch_profile(provider, access_token)
        profile = oauth_providers.normalize_profile(provider, raw_profile)
    except OAuthError:
        return _error_redirect("provider_error")

    oauth_account = (
        db.query(OAuthAccount)
        .filter(OAuthAccount.provider == provider, OAuthAccount.provider_user_id == profile["provider_user_id"])
        .first()
    )

    if oauth_account is not None:
        user = db.get(User, oauth_account.user_id)
        if user is None or not user.is_active:
            return _error_redirect("account_disabled")
    else:
        # Первый вход через этого провайдера — заводим новую компанию с минимальным
        # тарифом (та же логика, что и в POST /auth/register-company), а не пытаемся
        # найти существующего пользователя по email: если у человека уже есть
        # обычный email/пароль-аккаунт с тем же email, это осознанное ограничение
        # v1 — слияние аккаунтов не реализовано, он получит отдельную компанию.
        company = Company(
            name=profile["full_name"], module_finance_enabled=True, module_warehouse_enabled=False
        )
        db.add(company)
        db.flush()

        user = User(
            email=profile.get("email"),
            full_name=profile["full_name"],
            hashed_password=None,
            # Провайдер уже подтвердил личность (и email, если он есть) за нас —
            # незачем гонять человека ещё и через self-hosted письмо.
            email_verified=True,
        )
        db.add(user)
        db.flush()
        db.add(CompanyMember(user_id=user.id, company_id=company.id, role=RoleEnum.admin))
        company.owner_user_id = user.id
        db.flush()

        oauth_account = OAuthAccount(user_id=user.id, provider=provider, provider_user_id=profile["provider_user_id"])
        db.add(oauth_account)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.id})
    return RedirectResponse(f"{settings.frontend_base_url}/oauth-callback#token={token}")
