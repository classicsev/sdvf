from app.models import RoleEnum
from tests.conftest import auth_headers, make_company, make_project, make_user


def test_create_user_and_duplicate_email_rejected(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post(
        "/users",
        headers=headers,
        json={"email": "new@test.local", "full_name": "Новый", "password": "pass1234", "role": "viewer"},
    )
    assert resp.status_code == 200, resp.text
    assert "password" not in resp.json()
    assert "hashed_password" not in resp.json()

    resp = client.post(
        "/users",
        headers=headers,
        json={"email": "new@test.local", "full_name": "Дубль", "password": "x", "role": "viewer"},
    )
    assert resp.status_code == 400


def test_update_user_role_and_project(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    project = make_project(db_session)
    target = make_user(db_session, RoleEnum.viewer, email="t@test.local")

    resp = client.patch(
        f"/users/{target.id}",
        headers=headers,
        json={"role": "project_manager", "project_id": project.id},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "project_manager"
    assert resp.json()["project_id"] == project.id


def test_update_user_password_actually_changes_login(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    target = make_user(db_session, RoleEnum.viewer, email="t@test.local", password="old-pass")

    resp = client.patch(f"/users/{target.id}", headers=auth_headers(admin), json={"password": "new-pass"})
    assert resp.status_code == 200

    resp = client.post("/auth/login", json={"email": "t@test.local", "password": "old-pass"})
    assert resp.status_code == 401

    resp = client.post("/auth/login", json={"email": "t@test.local", "password": "new-pass"})
    assert resp.status_code == 200


def test_admin_cannot_change_own_role(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.patch(f"/users/{admin.id}", headers=auth_headers(admin), json={"role": "viewer"})
    assert resp.status_code == 400


def test_deactivate_and_reactivate_user(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = make_user(db_session, RoleEnum.viewer, email="t@test.local", password="pass1234")

    resp = client.delete(f"/users/{target.id}", headers=headers)
    assert resp.status_code == 200

    resp = client.post("/auth/login", json={"email": "t@test.local", "password": "pass1234"})
    assert resp.status_code == 401

    resp = client.patch(f"/users/{target.id}", headers=headers, json={"is_active": True})
    assert resp.status_code == 200

    resp = client.post("/auth/login", json={"email": "t@test.local", "password": "pass1234"})
    assert resp.status_code == 200


def test_malformed_uuid_on_user_returns_404(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.patch("/users/not-a-uuid", headers=auth_headers(admin), json={"full_name": "x"})
    assert resp.status_code == 404


def test_manage_users_in_second_company_via_company_id(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    resp = client.post("/companies", json={"name": "Компания Б"}, headers=headers)
    assert resp.status_code == 201, resp.text
    company_b = resp.json()["company"]["id"]

    # Список без ?company_id= — сводно по обеим компаниям admin.
    resp = client.get("/users", headers=headers)
    assert resp.status_code == 200
    assert any(u["id"] == admin.id for u in resp.json())

    # Создание в конкретной, не первичной, компании.
    resp = client.post(
        "/users",
        params={"company_id": company_b},
        headers=headers,
        json={"email": "b-user@test.local", "full_name": "Б Сотрудник", "password": "pass1234", "role": "viewer"},
    )
    assert resp.status_code == 200, resp.text
    new_user_id = resp.json()["id"]

    resp = client.get("/users", params={"company_id": company_b}, headers=headers)
    assert resp.status_code == 200
    assert any(u["id"] == new_user_id for u in resp.json())

    resp = client.patch(
        f"/users/{new_user_id}",
        params={"company_id": company_b},
        headers=headers,
        json={"role": "operator"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "operator"


def test_cannot_manage_users_in_company_without_access(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other_company = make_company(db_session, name="Чужая компания")
    other_admin = make_user(db_session, RoleEnum.admin, company_id=other_company.id)

    resp = client.get("/users", params={"company_id": other_company.id}, headers=auth_headers(admin))
    assert resp.status_code == 404

    resp = client.patch(
        f"/users/{other_admin.id}",
        params={"company_id": other_company.id},
        headers=auth_headers(admin),
        json={"role": "viewer"},
    )
    assert resp.status_code == 404
