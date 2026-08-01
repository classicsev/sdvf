from app.models import RoleEnum
from tests.conftest import auth_headers, make_user


def test_login_success(client, db_session):
    make_user(db_session, RoleEnum.admin, email="a@test.local", password="secret123")

    resp = client.post("/auth/login", json={"email": "a@test.local", "password": "secret123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client, db_session):
    make_user(db_session, RoleEnum.admin, email="a@test.local", password="secret123")

    resp = client.post("/auth/login", json={"email": "a@test.local", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_email(client, db_session):
    resp = client.post("/auth/login", json={"email": "nobody@test.local", "password": "x"})
    assert resp.status_code == 401


def test_deactivated_user_cannot_login(client, db_session):
    make_user(db_session, RoleEnum.admin, email="a@test.local", password="secret123", is_active=False)

    resp = client.post("/auth/login", json={"email": "a@test.local", "password": "secret123"})
    assert resp.status_code == 401
    assert "деактивирована" in resp.json()["detail"]


def test_deactivated_user_token_rejected_on_protected_route(client, db_session):
    user = make_user(db_session, RoleEnum.admin, email="a@test.local")
    headers = auth_headers(user)

    # Токен выпущен, пока пользователь ещё активен — деактивируем после
    user.is_active = False
    db_session.commit()

    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 401


def test_no_token_rejected(client, db_session):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_non_admin_cannot_list_users(client, db_session):
    viewer = make_user(db_session, RoleEnum.viewer)
    resp = client.get("/users", headers=auth_headers(viewer))
    assert resp.status_code == 403


def test_admin_cannot_deactivate_self(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.delete(f"/users/{admin.id}", headers=auth_headers(admin))
    assert resp.status_code == 400
