from app.models import CompanyMember, RoleEnum, User
from tests.conftest import auth_headers, make_company, make_user


def test_login_oauth_only_account_returns_401_not_500(client, db_session):
    # Пользователь, заведённый через VK ID/Яндекс ID — hashed_password=None.
    # verify_password() падает на None-хэше, а не возвращает False — важно,
    # чтобы login() перехватывал это раньше, иначе был бы 500 вместо 401.
    user = make_user(db_session, RoleEnum.admin, email="oauth-only@test.local")
    user.hashed_password = None
    db_session.commit()

    resp = client.post("/auth/login", json={"email": "oauth-only@test.local", "password": "anything"})
    assert resp.status_code == 401


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


def test_require_module_allows_access_when_module_enabled_in_any_company(client, db_session):
    # Пользователь с двумя компаниями: finance выключен в первой, включен во второй.
    # Доступ к /accounts должен быть, т.к. require_module смотрит все доступные компании.
    user = make_user(db_session, RoleEnum.admin)
    first_membership = user.company_memberships[0]
    first_company = first_membership.company
    first_company.module_finance_enabled = False

    second_company = make_company(db_session, name="Вторая компания")
    db_session.add(CompanyMember(user_id=user.id, company_id=second_company.id, role=RoleEnum.admin))
    db_session.commit()

    resp = client.get("/accounts", headers=auth_headers(user))
    assert resp.status_code == 200


def test_require_module_rejects_when_module_disabled_in_all_companies(client, db_session):
    user = make_user(db_session, RoleEnum.admin)
    for membership in user.company_memberships:
        membership.company.module_finance_enabled = False
    db_session.commit()

    resp = client.get("/accounts", headers=auth_headers(user))
    assert resp.status_code == 403
