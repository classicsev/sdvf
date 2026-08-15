from app.auth import (
    create_access_token,
    create_email_verification_token,
    create_sso_link_confirm_token,
    decode_sso_identity_code,
)
from app.config import settings
from app.models import RoleEnum
from tests.conftest import auth_headers, make_user

REDIRECT_URI = "https://sdvf.ru/auth/sso/callback"
LINK_REDIRECT_URI = "https://sdvf.ru/auth/sso/link-callback"
CLIENT_SECRET = "test-sso-secret"


def _configure_sso(monkeypatch):
    monkeypatch.setattr(settings, "sdvf_sso_redirect_uri", REDIRECT_URI)
    monkeypatch.setattr(settings, "sdvf_sso_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(settings, "sdvf_sso_link_redirect_uri", LINK_REDIRECT_URI)


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
    # По умолчанию (без ?purpose=) — обычный вход, не привязка
    assert "purpose=login" in location


def test_authorize_accepts_link_redirect_uri_with_purpose(client, monkeypatch):
    # Второй доверенный колбэк — для привязки аккаунта (см. LINK_REDIRECT_URI),
    # тот же allowlist, что и для входа, но отдельное значение.
    _configure_sso(monkeypatch)
    resp = client.get(
        "/oauth/authorize",
        params={"redirect_uri": LINK_REDIRECT_URI, "state": "s1", "purpose": "link"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert f"redirect_uri={LINK_REDIRECT_URI}".replace(":", "%3A").replace("/", "%2F") in location or LINK_REDIRECT_URI in location
    assert "purpose=link" in location


def test_authorize_rejects_link_uri_when_not_configured(client, monkeypatch):
    # Настроен только обычный вход, привязка ещё не настроена (sdvf_sso_link_redirect_uri="")
    monkeypatch.setattr(settings, "sdvf_sso_redirect_uri", REDIRECT_URI)
    monkeypatch.setattr(settings, "sdvf_sso_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(settings, "sdvf_sso_link_redirect_uri", "")
    resp = client.get(
        "/oauth/authorize", params={"redirect_uri": LINK_REDIRECT_URI, "state": "s1", "purpose": "link"}
    )
    assert resp.status_code == 400


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


# ---------------------------------------------------------------------------
# purpose=link — привязка аккаунта: code не выдаётся сразу (в отличие от
# входа), а только после перехода по ссылке из письма. Активной сессии в
# браузере недостаточно — она могла остаться от другого человека на этом
# устройстве (см. docstring модуля).
# ---------------------------------------------------------------------------


def test_consent_link_purpose_sends_email_instead_of_redirect(client, db_session, monkeypatch):
    _configure_sso(monkeypatch)
    sent = {}
    monkeypatch.setattr(
        "app.routers.identity_provider.send_sso_link_confirmation_email",
        lambda to_email, token, client_name: sent.update(to=to_email, token=token) or True,
    )
    user = make_user(db_session, RoleEnum.admin, email="linker@test.local")
    user.email_verified = True
    db_session.commit()

    resp = client.post(
        "/oauth/consent",
        headers=auth_headers(user),
        json={"redirect_uri": LINK_REDIRECT_URI, "state": "s1", "purpose": "link"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email_sent_to"] == "linker@test.local"
    assert body["redirect_url"] is None
    assert sent["to"] == "linker@test.local"


def test_consent_link_purpose_requires_verified_email(client, db_session, monkeypatch):
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin, email="unverified@test.local")
    user.email_verified = False
    db_session.commit()

    resp = client.post(
        "/oauth/consent",
        headers=auth_headers(user),
        json={"redirect_uri": LINK_REDIRECT_URI, "state": "s1", "purpose": "link"},
    )
    assert resp.status_code == 400


def test_link_confirm_redirects_with_code_for_valid_token(client, db_session, monkeypatch):
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin)
    token = create_sso_link_confirm_token(user.id, LINK_REDIRECT_URI, "s1")

    resp = client.get("/oauth/link-confirm", params={"token": token}, follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith(f"{LINK_REDIRECT_URI}?")
    assert "state=s1" in location

    code = location.split("code=")[1].split("&")[0]
    assert decode_sso_identity_code(code) == user.id


def test_link_confirm_rejects_expired_or_invalid_token(client, monkeypatch):
    _configure_sso(monkeypatch)
    resp = client.get("/oauth/link-confirm", params={"token": "not-a-real-token"})
    assert resp.status_code == 400


def test_link_confirm_rejects_wrong_purpose_token(client, db_session, monkeypatch):
    # Ссылка подтверждения email из /auth/register — валидный JWT, но не тот
    # purpose, что нужен для завершения привязки.
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin)
    wrong_purpose_token = create_email_verification_token(user.id)

    resp = client.get("/oauth/link-confirm", params={"token": wrong_purpose_token})
    assert resp.status_code == 400


def test_link_confirm_revalidates_redirect_uri_allowlist(client, db_session, monkeypatch):
    # Токен подписан на редирект, который был в allowlist на момент отправки
    # письма — если allowlist с тех пор сузился, ссылка больше не должна работать.
    _configure_sso(monkeypatch)
    user = make_user(db_session, RoleEnum.admin)
    token = create_sso_link_confirm_token(user.id, LINK_REDIRECT_URI, "s1")

    monkeypatch.setattr(settings, "sdvf_sso_link_redirect_uri", "")
    resp = client.get("/oauth/link-confirm", params={"token": token})
    assert resp.status_code == 400


def test_full_link_flow_end_to_end(client, db_session, monkeypatch):
    """Полный путь: consent(purpose=link) -> письмо -> переход по ссылке ->
    code -> /oauth/token отдаёт ту же личность, что и обычный вход."""
    _configure_sso(monkeypatch)
    captured = {}
    monkeypatch.setattr(
        "app.routers.identity_provider.send_sso_link_confirmation_email",
        lambda to_email, token, client_name: captured.update(token=token) or True,
    )
    user = make_user(db_session, RoleEnum.admin, email="e2e@test.local")
    user.email_verified = True
    db_session.commit()

    consent_resp = client.post(
        "/oauth/consent",
        headers=auth_headers(user),
        json={"redirect_uri": LINK_REDIRECT_URI, "state": "s1", "purpose": "link"},
    )
    assert consent_resp.status_code == 200

    confirm_resp = client.get(
        "/oauth/link-confirm", params={"token": captured["token"]}, follow_redirects=False
    )
    code = confirm_resp.headers["location"].split("code=")[1].split("&")[0]

    token_resp = client.post("/oauth/token", json={"code": code, "client_secret": CLIENT_SECRET})
    assert token_resp.status_code == 200
    assert token_resp.json()["user_id"] == user.id
    assert token_resp.json()["email"] == "e2e@test.local"
