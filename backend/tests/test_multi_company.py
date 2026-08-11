from app.models import RoleEnum
from tests.conftest import auth_headers, make_company, make_user


# ---------------------------------------------------------------------------
# Создание дополнительных компаний и просмотр списка своих компаний
# ---------------------------------------------------------------------------


def test_create_second_company_makes_creator_admin(client, db_session):
    user = make_user(db_session, RoleEnum.viewer)
    headers = auth_headers(user)

    resp = client.post("/companies", json={"name": "Вторая компания"}, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["company"]["name"] == "Вторая компания"
    assert body["role"] == "admin"


def test_create_individual_company_type(client, db_session):
    user = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(user)

    resp = client.post(
        "/companies", json={"name": "Личные счета", "company_type": "individual"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["company"]["company_type"] == "individual"


def test_create_company_rejects_invalid_type(client, db_session):
    user = make_user(db_session, RoleEnum.admin)
    resp = client.post(
        "/companies", json={"name": "X", "company_type": "bogus"}, headers=auth_headers(user)
    )
    assert resp.status_code == 400


def test_list_my_companies_shows_all_memberships(client, db_session):
    user = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(user)
    client.post("/companies", json={"name": "Компания 2"}, headers=headers)
    client.post("/companies", json={"name": "Компания 3"}, headers=headers)

    resp = client.get("/companies", headers=headers)
    assert resp.status_code == 200
    names = {row["company"]["name"] for row in resp.json()}
    assert len(resp.json()) == 3
    assert "Компания 2" in names and "Компания 3" in names


def test_user_only_sees_own_companies(client, db_session):
    user_a = make_user(db_session, RoleEnum.admin)
    user_b = make_user(db_session, RoleEnum.admin)
    client.post("/companies", json={"name": "Компания A2"}, headers=auth_headers(user_a))

    resp = client.get("/companies", headers=auth_headers(user_b))
    assert resp.status_code == 200
    assert len(resp.json()) == 1  # только своя первая компания


# ---------------------------------------------------------------------------
# Приглашение участников в компанию
# ---------------------------------------------------------------------------


def test_add_existing_user_as_member(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other_company = make_company(db_session, name="Компания other")
    other = make_user(db_session, RoleEnum.viewer, email="other@test.local", company_id=other_company.id)
    company_id = admin.company_id

    resp = client.post(
        f"/companies/{company_id}/members",
        json={"email": "other@test.local", "role": "operator"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "operator"

    # У other теперь доступ к двум компаниям — своей и той, куда его добавили
    resp2 = client.get("/companies", headers=auth_headers(other))
    assert len(resp2.json()) == 2


def test_add_new_user_creates_account(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.post(
        f"/companies/{admin.company_id}/members",
        json={
            "email": "brandnew@test.local",
            "role": "viewer",
            "full_name": "Новый Сотрудник",
            "password": "test1234",
        },
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201, resp.text

    login_resp = client.post(
        "/auth/login", json={"email": "brandnew@test.local", "password": "test1234"}
    )
    assert login_resp.status_code == 200


def test_add_new_user_without_password_rejected(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.post(
        f"/companies/{admin.company_id}/members",
        json={"email": "nopass@test.local", "role": "viewer"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 400


def test_add_member_duplicate_rejected(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other = make_user(db_session, RoleEnum.viewer, email="dup@test.local", company_id=admin.company_id)

    resp = client.post(
        f"/companies/{admin.company_id}/members",
        json={"email": "dup@test.local", "role": "operator"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 400


def test_non_admin_cannot_add_member(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer, company_id=admin.company_id)

    resp = client.post(
        f"/companies/{admin.company_id}/members",
        json={"email": "x@test.local", "role": "viewer", "full_name": "X", "password": "test1234"},
        headers=auth_headers(viewer),
    )
    assert resp.status_code == 403


def test_admin_in_one_company_cannot_manage_another(client, db_session):
    admin_a = make_user(db_session, RoleEnum.admin)
    company_b = make_company(db_session, name="Чужая компания")

    resp = client.post(
        f"/companies/{company_b.id}/members",
        json={"email": "x@test.local", "role": "viewer", "full_name": "X", "password": "test1234"},
        headers=auth_headers(admin_a),
    )
    assert resp.status_code == 404  # не палим существование чужой компании


# ---------------------------------------------------------------------------
# Изменение роли / отзыв доступа
# ---------------------------------------------------------------------------


def test_update_member_role(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other = make_user(db_session, RoleEnum.viewer, company_id=admin.company_id)

    resp = client.patch(
        f"/companies/{admin.company_id}/members/{other.id}",
        json={"role": "operator"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "operator"


def test_cannot_change_own_role(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.patch(
        f"/companies/{admin.company_id}/members/{admin.id}",
        json={"role": "viewer"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 400


def test_remove_member_revokes_access(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other = make_user(db_session, RoleEnum.viewer, company_id=admin.company_id)

    resp = client.delete(f"/companies/{admin.company_id}/members/{other.id}", headers=auth_headers(admin))
    assert resp.status_code == 200

    # other больше не видит эту компанию
    resp2 = client.get("/companies", headers=auth_headers(other))
    assert resp2.json() == []


def test_cannot_remove_last_admin(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.delete(f"/companies/{admin.company_id}/members/{admin.id}", headers=auth_headers(admin))
    assert resp.status_code == 400


def test_can_remove_admin_when_another_admin_remains(client, db_session):
    admin1 = make_user(db_session, RoleEnum.admin)
    admin2 = make_user(db_session, RoleEnum.admin, company_id=admin1.company_id)

    resp = client.delete(
        f"/companies/{admin1.company_id}/members/{admin2.id}", headers=auth_headers(admin1)
    )
    assert resp.status_code == 200


def test_malformed_uuid_returns_404_not_500(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.patch(
        f"/companies/{admin.company_id}/members/not-a-uuid",
        json={"role": "viewer"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 404
