from app.auth import create_access_token, create_email_verification_token
from app.models import RoleEnum
from tests.conftest import auth_headers, make_user

REGISTER_PAYLOAD = {
    "company_name": "Новая компания",
    "admin_email": "founder@test.local",
    "admin_full_name": "Основатель",
    "admin_password": "secret123",
    "pdn_consent": True,
}


def test_register_company_sends_verification_email(client, monkeypatch):
    sent = {}

    def fake_send(to_email, token):
        sent["to_email"] = to_email
        sent["token"] = token
        return True

    monkeypatch.setattr("app.routers.users.send_verification_email", fake_send)

    resp = client.post("/auth/register-company", json=REGISTER_PAYLOAD)
    assert resp.status_code == 200
    assert sent["to_email"] == "founder@test.local"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"})
    assert me.json()["email_verified"] is False


def test_register_company_succeeds_even_if_email_send_fails(client, monkeypatch):
    # Сбой SMTP не должен ронять регистрацию — аккаунт уже создан к моменту отправки.
    monkeypatch.setattr("app.routers.users.send_verification_email", lambda to_email, token: False)

    resp = client.post(
        "/auth/register-company",
        json={**REGISTER_PAYLOAD, "admin_email": "resilient@test.local"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_verify_email_with_valid_token(client, db_session):
    user = make_user(db_session, RoleEnum.admin, email="unverified@test.local")
    assert user.email_verified is False
    token = create_email_verification_token(user.id)

    resp = client.get("/auth/verify-email", params={"token": token})
    assert resp.status_code == 200
    assert resp.json() == {"verified": True}

    db_session.refresh(user)
    assert user.email_verified is True


def test_verify_email_with_garbage_token_returns_400(client):
    resp = client.get("/auth/verify-email", params={"token": "not-a-real-token"})
    assert resp.status_code == 400


def test_verify_email_rejects_regular_access_token(client, db_session):
    # Обычный access-токен не должен работать как ссылка подтверждения —
    # purpose-claim в create_email_verification_token/decode_email_verification_token
    # как раз и защищает от этой подмены.
    user = make_user(db_session, RoleEnum.admin)
    access_token = create_access_token({"sub": user.id, "role": user.role.value})

    resp = client.get("/auth/verify-email", params={"token": access_token})
    assert resp.status_code == 400


def test_resend_verification_when_unverified(client, db_session, monkeypatch):
    sent = {}

    def fake_send(to_email, token):
        sent["to_email"] = to_email
        return True

    monkeypatch.setattr("app.routers.users.send_verification_email", fake_send)
    user = make_user(db_session, RoleEnum.admin, email="pending@test.local")

    resp = client.post("/auth/resend-verification", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert sent["to_email"] == "pending@test.local"


def test_resend_verification_when_already_verified(client, db_session):
    user = make_user(db_session, RoleEnum.admin, email="already@test.local")
    user.email_verified = True
    db_session.commit()

    resp = client.post("/auth/resend-verification", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json() == {"sent": False, "reason": "already_verified"}


def test_resend_verification_requires_auth(client):
    resp = client.post("/auth/resend-verification")
    assert resp.status_code == 401
