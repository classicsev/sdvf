from app.auth import create_access_token, create_email_verification_token, decode_sso_identity_code
from app.config import settings
from app.models import RoleEnum
from tests.conftest import auth_headers, make_user

REDIRECT_URI = "https://sdvf.ru/auth/sso/callback"
CLIENT_SECRET = "test-sso-secret"


def _configure_sso(monkeypatch):
    monkeypatch.setattr(settings, "sdvf_sso_redirect_uri", REDIRECT_URI)
    monkeypatch.setattr(settings, "sdvf_sso_client_secret", CLIENT_SECRET)


def test_authorize_503_when_not_configured(client):
    resp = client.get("/oauth/authorize", params={"redirect_uri": REDIRECT_URI, "state": "s1"})
    assert resp.status_code == 503


def test_authorize_rejects_unknown_redirect_uri(client, monkeypatch):
    _configure_sso(monkeypatch)
    resp = client.get("/oauth/authorize", params={"redirect_uri": "https://evil.example/cb", "state": "s1"})
    assert resp.status_code == 400


def test_authorize_redirects_to_consent_page(client, monkeypatch):
    _configure_sso(monkeypatch)
    resp = client.get(
        "/oauth/authorize", params={"redirect_uri": REDIRECT_URI, "state": "s1"}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith(f"{settings.frontend_base_url}/sso-consent?")
    assert "state=s1" in location
    assert "client=sdvf" in location


def test_consent_requires_auth(client, monkeypatch):
    _configure_sso(monkeypatch)
    resp = client.post("/oauth/consent", json={"redirect_uri": REDIRECT_URI, "state": "s1"})
    assert resp.status_code == 401


def test_consent_rejects_unknown_redirect_uri(client, db_session, monkeypatch):
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin)
    resp = client.post(
        "/oauth/consent",
        headers=auth_headers(user),
        json={"redirect_uri": "https://evil.example/cb", "state": "s1"},
    )
    assert resp.status_code == 400


def test_consent_happy_path_issues_code_for_the_logged_in_user(client, db_session, monkeypatch):
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin, email="sso-user@test.local")

    resp = client.post(
        "/oauth/consent",
        headers=auth_headers(user),
        json={"redirect_uri": REDIRECT_URI, "state": "s1"},
    )
    assert resp.status_code == 200, resp.text
    redirect_url = resp.json()["redirect_url"]
    assert redirect_url.startswith(f"{REDIRECT_URI}?")
    assert "state=s1" in redirect_url

    code = redirect_url.split("code=")[1].split("&")[0]
    assert decode_sso_identity_code(code) == user.id


def test_token_rejects_wrong_client_secret(client, db_session, monkeypatch):
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin)
    consent_resp = client.post(
        "/oauth/consent", headers=auth_headers(user), json={"redirect_uri": REDIRECT_URI, "state": "s1"}
    )
    code = consent_resp.json()["redirect_url"].split("code=")[1].split("&")[0]

    resp = client.post("/oauth/token", json={"code": code, "client_secret": "wrong"})
    assert resp.status_code == 401


def test_token_rejects_invalid_code(client, monkeypatch):
    _configure_sso(monkeypatch)
    resp = client.post("/oauth/token", json={"code": "not-a-real-code", "client_secret": CLIENT_SECRET})
    assert resp.status_code == 400


def test_token_rejects_wrong_purpose_code(client, db_session, monkeypatch):
    # Токен подтверждения email — валидный JWT, но не тот purpose, что нужен
    # /oauth/token — не должен быть принят вместо identity-кода.
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin)
    wrong_purpose_token = create_email_verification_token(user.id)

    resp = client.post("/oauth/token", json={"code": wrong_purpose_token, "client_secret": CLIENT_SECRET})
    assert resp.status_code == 400


def test_token_rejects_regular_access_token(client, db_session, monkeypatch):
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin)
    access_token = create_access_token({"sub": user.id, "role": user.role.value})

    resp = client.post("/oauth/token", json={"code": access_token, "client_secret": CLIENT_SECRET})
    assert resp.status_code == 400


def test_token_happy_path_returns_identity(client, db_session, monkeypatch):
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin, email="sso-user2@test.local")
    user.email_verified = True
    db_session.commit()

    consent_resp = client.post(
        "/oauth/consent", headers=auth_headers(user), json={"redirect_uri": REDIRECT_URI, "state": "s1"}
    )
    code = consent_resp.json()["redirect_url"].split("code=")[1].split("&")[0]

    resp = client.post("/oauth/token", json={"code": code, "client_secret": CLIENT_SECRET})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == user.id
    assert body["email"] == "sso-user2@test.local"
    assert body["email_verified"] is True


def test_token_503_when_not_configured(client):
    resp = client.post("/oauth/token", json={"code": "x", "client_secret": "y"})
    assert resp.status_code == 503
