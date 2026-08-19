import httpx

from app.auth import create_access_token, create_oauth_state_token
from app.config import settings
from app.models import OAuthAccount, RoleEnum, User
from tests.conftest import make_company, make_user


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "sdvf_base_url", "https://sdvf.ru")
    monkeypatch.setattr(settings, "sdvf_client_secret", "shared-secret")


def test_enabled_reflects_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "sdvf_base_url", "")
    monkeypatch.setattr(settings, "sdvf_client_secret", "")
    assert client.get("/auth/sdvf/enabled").json() == {"enabled": False}

    _configure(monkeypatch)
    assert client.get("/auth/sdvf/enabled").json() == {"enabled": True}


def test_start_redirects_to_error_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "sdvf_base_url", "")
    resp = client.get("/auth/sdvf/start", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "error=provider_not_configured" in resp.headers["location"]


def test_start_redirects_to_sdvf_authorize_url(client, monkeypatch):
    _configure(monkeypatch)
    resp = client.get("/auth/sdvf/start", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://sdvf.ru/oauth/authorize?")
    assert "state=" in location
    assert "redirect_uri=" in location


def test_callback_first_login_creates_company_and_user(client, db_session, monkeypatch):
    _configure(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        assert url == "https://sdvf.ru/oauth/token"
        assert json == {"code": "auth-code-1", "client_secret": "shared-secret"}
        return _FakeResponse(200, {
            "user_id": 42,
            "email": "person@sdvf.ru",
            "email_verified": True,
            "full_name": "Пользователь СДВФ",
            "uchet_user_id": None,
        })

    monkeypatch.setattr(httpx, "post", fake_post)

    state = create_oauth_state_token("sdvf")
    resp = client.get(
        "/auth/sdvf/callback", params={"code": "auth-code-1", "state": state}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].startswith(f"{settings.frontend_base_url}/oauth-callback#token=")

    user = db_session.query(User).filter(User.email == "person@sdvf.ru").first()
    assert user is not None
    assert user.email_verified is True
    assert user.hashed_password is None

    oauth_account = db_session.query(OAuthAccount).filter(
        OAuthAccount.provider == "sdvf", OAuthAccount.provider_user_id == "42"
    ).first()
    assert oauth_account is not None
    assert oauth_account.user_id == user.id


def test_callback_second_login_reuses_existing_account(client, db_session, monkeypatch):
    _configure(monkeypatch)

    def make_fake_post(user_id):
        def fake_post(url, json=None, timeout=None):
            return _FakeResponse(200, {
                "user_id": user_id,
                "email": "repeat@sdvf.ru",
                "email_verified": True,
                "full_name": "Повторный Вход",
                "uchet_user_id": None,
            })
        return fake_post

    for code in ("c1", "c2"):
        monkeypatch.setattr(httpx, "post", make_fake_post(777))
        state = create_oauth_state_token("sdvf")
        resp = client.get("/auth/sdvf/callback", params={"code": code, "state": state}, follow_redirects=False)
        assert resp.status_code in (302, 307)

    assert db_session.query(User).filter(User.email == "repeat@sdvf.ru").count() == 1
    assert db_session.query(OAuthAccount).filter(OAuthAccount.provider_user_id == "777").count() == 1


def test_callback_with_uchet_user_id_logs_into_already_linked_account(client, db_session, monkeypatch):
    # Пользователь уже привязал свой аккаунт СДВФ к аккаунту Учёта (через
    # профиль СДВФ) — токен-ответ несёт uchet_user_id, вход должен попасть
    # ровно в этот существующий User, а не завести новый.
    _configure(monkeypatch)
    company = make_company(db_session, "Existing Co")
    existing_user = make_user(db_session, RoleEnum.admin, company_id=company.id, email="already@here.ru")

    def fake_post(url, json=None, timeout=None):
        return _FakeResponse(200, {
            "user_id": 555,
            "email": "sdvf-side-email@sdvf.ru",
            "email_verified": True,
            "full_name": "СДВФ Профиль",
            "uchet_user_id": existing_user.id,
        })

    monkeypatch.setattr(httpx, "post", fake_post)

    state = create_oauth_state_token("sdvf")
    resp = client.get("/auth/sdvf/callback", params={"code": "link-code", "state": state}, follow_redirects=False)
    assert resp.status_code in (302, 307)

    # Никакого нового пользователя/OAuthAccount не появилось.
    assert db_session.query(User).filter(User.email == "sdvf-side-email@sdvf.ru").count() == 0
    assert db_session.query(OAuthAccount).filter(OAuthAccount.provider == "sdvf").count() == 0

    token = resp.headers["location"].split("#token=")[1]

    # Токен выдан на существующего пользователя, не на нового.
    import jose.jwt as jwt

    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == existing_user.id


def test_callback_rejects_invalid_state(client, monkeypatch):
    _configure(monkeypatch)
    resp = client.get(
        "/auth/sdvf/callback", params={"code": "c1", "state": "garbage"}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    assert "error=invalid_state" in resp.headers["location"]


def test_callback_provider_denied_redirects_with_error(client):
    resp = client.get(
        "/auth/sdvf/callback", params={"error": "access_denied", "state": "irrelevant"}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    assert "error=provider_denied" in resp.headers["location"]


def test_callback_token_endpoint_failure_redirects_gracefully(client, monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse(500, {}))

    state = create_oauth_state_token("sdvf")
    resp = client.get("/auth/sdvf/callback", params={"code": "c1", "state": state}, follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "error=provider_error" in resp.headers["location"]


def test_callback_rejects_unverified_email(client, monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **kw: _FakeResponse(200, {
            "user_id": 1, "email": "x@sdvf.ru", "email_verified": False, "full_name": "X", "uchet_user_id": None,
        }),
    )

    state = create_oauth_state_token("sdvf")
    resp = client.get("/auth/sdvf/callback", params={"code": "c1", "state": state}, follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "error=email_not_verified" in resp.headers["location"]
