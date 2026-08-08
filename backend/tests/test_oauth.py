from app.auth import create_oauth_state_token
from app.config import settings
from app.integrations import oauth_providers
from app.models import OAuthAccount, User


def _configure_yandex(monkeypatch):
    monkeypatch.setattr(settings, "yandex_client_id", "yandex-cid")
    monkeypatch.setattr(settings, "yandex_client_secret", "yandex-secret")


def test_providers_list_only_shows_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "vk_client_id", "")
    monkeypatch.setattr(settings, "sber_client_id", "")
    _configure_yandex(monkeypatch)

    resp = client.get("/auth/oauth/providers")
    assert resp.json() == {"providers": ["yandex"]}


def test_oauth_start_404_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "vk_client_id", "")
    resp = client.get("/auth/oauth/vk/start", follow_redirects=False)
    assert resp.status_code == 404


def test_oauth_start_redirects_to_authorize_url(client, monkeypatch):
    _configure_yandex(monkeypatch)
    resp = client.get("/auth/oauth/yandex/start", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://oauth.yandex.ru/authorize?")
    assert "client_id=yandex-cid" in location
    assert "state=" in location


def test_oauth_start_vk_includes_pkce_challenge(client, monkeypatch):
    # У VK ID (OAuth 2.1) обмен кода на токен идёт без client_secret — вместо
    # него защита строится на PKCE, поэтому /start обязан отдать code_challenge.
    monkeypatch.setattr(settings, "vk_client_id", "vk-cid")
    monkeypatch.setattr(settings, "vk_client_secret", "")

    resp = client.get("/auth/oauth/vk/start", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "code_challenge=" in location
    assert "code_challenge_method=S256" in location


def test_oauth_callback_first_login_creates_company_and_user(client, db_session, monkeypatch):
    _configure_yandex(monkeypatch)

    def fake_exchange_code(provider, code, redirect_uri, code_verifier=None, device_id=None):
        assert provider == "yandex"
        assert code == "auth-code-1"
        return {"access_token": "yandex-access-1"}

    def fake_fetch_profile(provider, access_token):
        assert access_token == "yandex-access-1"
        return {"id": "12345", "default_email": "newperson@yandex.ru", "real_name": "Новый Пользователь"}

    monkeypatch.setattr(oauth_providers, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(oauth_providers, "fetch_profile", fake_fetch_profile)

    state = create_oauth_state_token("yandex")
    resp = client.get(
        "/auth/oauth/yandex/callback",
        params={"code": "auth-code-1", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].startswith(f"{settings.frontend_base_url}/oauth-callback#token=")

    user = db_session.query(User).filter(User.email == "newperson@yandex.ru").first()
    assert user is not None
    assert user.email_verified is True  # провайдер уже подтвердил email за нас
    assert user.hashed_password is None
    assert user.full_name == "Новый Пользователь"

    oauth_account = db_session.query(OAuthAccount).filter(OAuthAccount.provider_user_id == "12345").first()
    assert oauth_account is not None
    assert oauth_account.user_id == user.id
    assert oauth_account.provider == "yandex"


def test_oauth_callback_second_login_reuses_existing_account(client, db_session, monkeypatch):
    _configure_yandex(monkeypatch)
    monkeypatch.setattr(oauth_providers, "exchange_code", lambda *a, **kw: {"access_token": "tok"})
    monkeypatch.setattr(
        oauth_providers,
        "fetch_profile",
        lambda *a, **kw: {"id": "999", "default_email": "repeat@yandex.ru", "real_name": "Повторный Вход"},
    )

    for code in ("c1", "c2"):
        state = create_oauth_state_token("yandex")
        resp = client.get(
            "/auth/oauth/yandex/callback", params={"code": code, "state": state}, follow_redirects=False
        )
        assert resp.status_code in (302, 307)

    # Второй вход через тот же provider_user_id не должен плодить второго пользователя/компанию.
    assert db_session.query(User).filter(User.email == "repeat@yandex.ru").count() == 1
    assert db_session.query(OAuthAccount).filter(OAuthAccount.provider_user_id == "999").count() == 1


def test_oauth_callback_different_providers_same_provider_user_id_are_distinct(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "vk_client_id", "vk-cid")
    monkeypatch.setattr(settings, "vk_client_secret", "")
    _configure_yandex(monkeypatch)

    monkeypatch.setattr(oauth_providers, "exchange_code", lambda *a, **kw: {"access_token": "vk-token"})
    monkeypatch.setattr(
        oauth_providers,
        "fetch_profile",
        lambda *a, **kw: {"user": {"user_id": "42", "email": "vk@example.ru", "first_name": "VK", "last_name": "U"}},
    )
    vk_state = create_oauth_state_token("vk", code_verifier="verifier-1")
    vk_resp = client.get(
        "/auth/oauth/vk/callback",
        params={"code": "vk-code", "state": vk_state, "device_id": "dev-1"},
        follow_redirects=False,
    )
    assert vk_resp.status_code in (302, 307)

    monkeypatch.setattr(oauth_providers, "exchange_code", lambda *a, **kw: {"access_token": "yandex-token"})
    monkeypatch.setattr(
        oauth_providers,
        "fetch_profile",
        lambda *a, **kw: {"id": "42", "default_email": "yandex@example.ru", "real_name": "Yandex U"},
    )
    yandex_state = create_oauth_state_token("yandex")
    yandex_resp = client.get(
        "/auth/oauth/yandex/callback", params={"code": "yandex-code", "state": yandex_state}, follow_redirects=False
    )
    assert yandex_resp.status_code in (302, 307)

    vk_account = (
        db_session.query(OAuthAccount)
        .filter(OAuthAccount.provider == "vk", OAuthAccount.provider_user_id == "42")
        .first()
    )
    yandex_account = (
        db_session.query(OAuthAccount)
        .filter(OAuthAccount.provider == "yandex", OAuthAccount.provider_user_id == "42")
        .first()
    )
    assert vk_account is not None and yandex_account is not None
    assert vk_account.user_id != yandex_account.user_id


def test_oauth_callback_rejects_state_for_wrong_provider(client, monkeypatch):
    _configure_yandex(monkeypatch)
    monkeypatch.setattr(settings, "vk_client_id", "vk-cid")

    state = create_oauth_state_token("vk")  # state минтился для vk...
    resp = client.get(
        "/auth/oauth/yandex/callback",  # ...а подсовывается на callback yandex
        params={"code": "code-1", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert "error=invalid_state" in resp.headers["location"]


def test_oauth_callback_provider_denied_redirects_with_error(client):
    resp = client.get(
        "/auth/oauth/yandex/callback",
        params={"error": "access_denied", "state": "irrelevant"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert "error=provider_denied" in resp.headers["location"]


def test_oauth_callback_provider_error_during_exchange_redirects_gracefully(client, monkeypatch):
    _configure_yandex(monkeypatch)

    def raise_error(*a, **kw):
        raise oauth_providers.OAuthError("boom")

    monkeypatch.setattr(oauth_providers, "exchange_code", raise_error)

    state = create_oauth_state_token("yandex")
    resp = client.get(
        "/auth/oauth/yandex/callback", params={"code": "c1", "state": state}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    assert "error=provider_error" in resp.headers["location"]
