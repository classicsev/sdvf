from app.models import RoleEnum
from tests.conftest import auth_headers, make_user


def test_category_full_crud(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post("/categories", headers=headers, json={"name": "Реклама", "type": "expense", "group_name": "OPEX"})
    assert resp.status_code == 200, resp.text
    category = resp.json()
    assert category["is_active"] is True

    resp = client.get("/categories", headers=headers)
    assert any(c["id"] == category["id"] for c in resp.json())

    resp = client.patch(
        f"/categories/{category['id']}",
        headers=headers,
        json={"name": "Реклама (изм.)", "type": "expense", "group_name": "OPEX"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Реклама (изм.)"

    resp = client.delete(f"/categories/{category['id']}", headers=headers)
    assert resp.status_code == 200

    resp = client.get("/categories", headers=headers)
    assert not any(c["id"] == category["id"] for c in resp.json())


def test_project_full_crud(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post("/projects", headers=headers, json={"name": "Проект X"})
    assert resp.status_code == 200
    project_id = resp.json()["id"]

    resp = client.patch(f"/projects/{project_id}", headers=headers, json={"name": "Проект Y"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Проект Y"

    resp = client.delete(f"/projects/{project_id}", headers=headers)
    assert resp.status_code == 200


def test_account_full_crud_with_account_number(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post(
        "/accounts",
        headers=headers,
        json={"name": "Р/с Альфа", "currency": "RUB", "opening_balance": 5000, "account_number": "40702810900000012345"},
    )
    assert resp.status_code == 200
    account = resp.json()
    assert account["account_number"] == "40702810900000012345"

    resp = client.patch(
        f"/accounts/{account['id']}",
        headers=headers,
        json={"name": "Р/с Альфа", "currency": "RUB", "opening_balance": 6000},
    )
    assert resp.status_code == 200
    assert resp.json()["opening_balance"] == 6000.0
    # account_number не передан в PATCH-payload -> AccountIn default None перезаписывает поле
    assert resp.json()["account_number"] is None


def test_counterparty_full_crud(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post("/counterparties", headers=headers, json={"name": "ИП Иванов", "type": "debtor", "inn": "123456789012"})
    assert resp.status_code == 200
    cp_id = resp.json()["id"]

    resp = client.patch(
        f"/counterparties/{cp_id}", headers=headers, json={"name": "ИП Иванов", "type": "creditor", "inn": "123456789012"}
    )
    assert resp.status_code == 200
    assert resp.json()["type"] == "creditor"

    resp = client.delete(f"/counterparties/{cp_id}", headers=headers)
    assert resp.status_code == 200


def test_operator_can_read_but_not_write_reference(client, db_session):
    operator = make_user(db_session, RoleEnum.operator)
    headers = auth_headers(operator)

    resp = client.get("/categories", headers=headers)
    assert resp.status_code == 200

    resp = client.post("/projects", headers=headers, json={"name": "x"})
    assert resp.status_code == 403
