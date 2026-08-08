import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings

TIMEOUT = 15.0


class OAuthError(Exception):
    pass


@dataclass
class ProviderConfig:
    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str
    # VK ID работает по OAuth 2.1: обязателен PKCE, а обмен code на токен идёт
    # БЕЗ client_secret (secret передаётся только Яндексом и Sber ID, у VK его
    # роль в защите от перехвата кода играет code_verifier).
    # Источник (официальная документация id.vk.ru, проверено вживую fetch'ем страниц):
    # authorize=https://id.vk.ru/authorize, token=https://id.vk.ru/oauth2/auth,
    # userinfo=https://id.vk.ru/oauth2/user_info.
    uses_pkce: bool = False
    extra_authorize_params: dict = field(default_factory=dict)


def _providers() -> dict[str, ProviderConfig]:
    return {
        "vk": ProviderConfig(
            name="vk",
            client_id=settings.vk_client_id,
            client_secret=settings.vk_client_secret,
            authorize_url="https://id.vk.ru/authorize",
            token_url="https://id.vk.ru/oauth2/auth",
            userinfo_url="https://id.vk.ru/oauth2/user_info",
            scope="email",
            uses_pkce=True,
        ),
        "yandex": ProviderConfig(
            name="yandex",
            client_id=settings.yandex_client_id,
            client_secret=settings.yandex_client_secret,
            authorize_url="https://oauth.yandex.ru/authorize",
            token_url="https://oauth.yandex.ru/token",
            userinfo_url="https://login.yandex.ru/info",
            scope="login:email login:info",
        ),
        # Sber ID (физлица, не путать с SberBusiness ID для организаций) —
        # источник: developers.sber.ru/docs/ru/sberid/... (проверено вживую fetch'ем
        # страниц документации). Заявка на подключение подана, но ещё не одобрена —
        # sber_client_id пуст, поэтому провайдер не показывается на фронте
        # (см. is_configured), пока не придёт client_id/secret от Сбера.
        "sber": ProviderConfig(
            name="sber",
            client_id=settings.sber_client_id,
            client_secret=settings.sber_client_secret,
            authorize_url="https://online.sberbank.ru/CSAFront/oidc/authorize.do",
            token_url="https://oauth.sber.ru/ru/prod/tokens/v2/oidc",
            userinfo_url="https://oauth.sber.ru/ru/prod/sberbankid/v2.1/userinfo",
            scope="openid name email phone",
            extra_authorize_params={"client_type": "PRIVATE", "nonce": ""},
        ),
    }


def get_provider(name: str) -> Optional[ProviderConfig]:
    return _providers().get(name)


def is_configured(name: str) -> bool:
    provider = get_provider(name)
    return bool(provider and provider.client_id)


def list_configured_providers() -> list[str]:
    return [name for name, provider in _providers().items() if provider.client_id]


def generate_pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge) для PKCE (S256) — нужен только VK ID."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(
    provider_name: str,
    redirect_uri: str,
    state: str,
    code_challenge: Optional[str] = None,
) -> str:
    provider = get_provider(provider_name)
    if provider is None or not provider.client_id:
        raise OAuthError(f"Провайдер {provider_name} не настроен")

    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "scope": provider.scope,
        "state": state,
        **provider.extra_authorize_params,
    }
    if provider.uses_pkce:
        if not code_challenge:
            raise OAuthError("Для VK ID обязателен code_challenge (PKCE)")
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    query = httpx.QueryParams(params)
    return f"{provider.authorize_url}?{query}"


def exchange_code(
    provider_name: str,
    code: str,
    redirect_uri: str,
    code_verifier: Optional[str] = None,
    device_id: Optional[str] = None,
) -> dict:
    """Обменивает authorization code на access_token. Формат запроса разный
    у каждого провайдера (см. ProviderConfig-комментарии выше), поэтому явные
    ветки вместо единой универсальной сборки параметров."""
    provider = get_provider(provider_name)
    if provider is None or not provider.client_id:
        raise OAuthError(f"Провайдер {provider_name} не настроен")

    if provider_name == "vk":
        if not code_verifier or not device_id:
            raise OAuthError("Для VK ID обязательны code_verifier и device_id")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": provider.client_id,
            "device_id": device_id,
            "redirect_uri": redirect_uri,
            "state": secrets.token_urlsafe(8),
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    elif provider_name == "yandex":
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    elif provider_name == "sber":
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "redirect_uri": redirect_uri,
            "scope": provider.scope,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "rquid": secrets.token_hex(16),
        }
    else:
        raise OAuthError(f"Неизвестный провайдер {provider_name}")

    try:
        resp = httpx.post(provider.token_url, data=data, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise OAuthError(f"Ошибка соединения с {provider_name} при обмене кода на токен: {exc}") from exc

    if resp.status_code != 200:
        raise OAuthError(f"{provider_name} вернул {resp.status_code} при обмене кода: {resp.text[:300]}")
    return resp.json()


def fetch_profile(provider_name: str, access_token: str) -> dict:
    provider = get_provider(provider_name)
    if provider is None:
        raise OAuthError(f"Неизвестный провайдер {provider_name}")

    if provider_name == "yandex":
        headers = {"Authorization": f"OAuth {access_token}"}
        params = None
    elif provider_name == "sber":
        headers = {"Authorization": f"Bearer {access_token}", "x-introspect-rquid": secrets.token_hex(16)}
        params = None
    else:  # vk
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"client_id": provider.client_id}

    try:
        resp = httpx.get(provider.userinfo_url, headers=headers, params=params, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise OAuthError(f"Ошибка соединения с {provider_name} при запросе профиля: {exc}") from exc

    if resp.status_code != 200:
        raise OAuthError(f"{provider_name} вернул {resp.status_code} при запросе профиля: {resp.text[:300]}")
    return resp.json()


def normalize_profile(provider_name: str, raw: dict) -> dict:
    """Приводит ответ каждого провайдера к общему виду
    {provider_user_id, email, full_name} — форма ответа у каждого своя."""
    if provider_name == "vk":
        # userinfo VK ID оборачивает данные в {"user": {...}}.
        user = raw.get("user", raw)
        user_id = user.get("user_id") or user.get("id")
        name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or None
        return {
            "provider_user_id": str(user_id),
            "email": user.get("email"),
            "full_name": name or "Пользователь VK",
        }
    if provider_name == "yandex":
        name = raw.get("real_name") or raw.get("display_name") or raw.get("login")
        return {
            "provider_user_id": str(raw.get("id")),
            "email": raw.get("default_email") or (raw.get("emails") or [None])[0],
            "full_name": name or "Пользователь Яндекс",
        }
    if provider_name == "sber":
        name = " ".join(filter(None, [raw.get("given_name"), raw.get("family_name")])) or None
        return {
            "provider_user_id": str(raw.get("sub")),
            "email": raw.get("email"),
            "full_name": name or "Пользователь Sber ID",
        }
    raise OAuthError(f"Неизвестный провайдер {provider_name}")
