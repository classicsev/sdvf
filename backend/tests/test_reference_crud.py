from datetime import date

from app.models import RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_project, make_user


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


def _post_transaction(client, headers, account_id, category_id):
    return client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": str(date.today()),
            "account_id": account_id,
            "category_id": category_id,
            "type": "expense",
            "amount": 100,
            "currency": "RUB",
        },
    )


def test_delete_category_in_use_deactivates_instead_of_erroring(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    category = make_category(db_session, tx_type=TxTypeEnum.expense)
    account = make_account(db_session)
    assert _post_transaction(client, headers, account.id, category.id).status_code == 200

    resp = client.delete(f"/categories/{category.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": False, "deactivated": True}

    updated = next(c for c in client.get("/categories", headers=headers).json() if c["id"] == category.id)
    assert updated["is_active"] is False


def test_delete_unused_category_still_physically_deletes(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    category = make_category(db_session, name="Неиспользуемая")

    resp = client.delete(f"/categories/{category.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True, "deactivated": False}
    assert not any(c["id"] == category.id for c in client.get("/categories", headers=headers).json())


def test_delete_account_in_use_deactivates(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    category = make_category(db_session)
    account = make_account(db_session)
    assert _post_transaction(client, headers, account.id, category.id).status_code == 200

    resp = client.delete(f"/accounts/{account.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": False, "deactivated": True}


def test_delete_counterparty_in_use_deactivates(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    category = make_category(db_session)
    account = make_account(db_session)
    counterparty_id = client.post(
        "/counterparties", headers=headers, json={"name": "ИП Тест", "type": "debtor"}
    ).json()["id"]
    tx_id = _post_transaction(client, headers, account.id, category.id).json()["id"]
    client.patch(f"/transactions/{tx_id}", headers=headers, json={"counterparty_id": counterparty_id})

    resp = client.delete(f"/counterparties/{counterparty_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": False, "deactivated": True}


def test_delete_project_used_by_project_manager_deactivates(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    project = make_project(db_session)
    make_user(db_session, RoleEnum.project_manager, project_id=project.id, email="pm-ref-test@test.local")

    resp = client.delete(f"/projects/{project.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": False, "deactivated": True}


def test_reactivate_deactivated_category_via_patch(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    category = make_category(db_session, name="Реклама")
    account = make_account(db_session)
    assert _post_transaction(client, headers, account.id, category.id).status_code == 200
    client.delete(f"/categories/{category.id}", headers=headers)

    resp = client.patch(
        f"/categories/{category.id}",
        headers=headers,
        json={"name": "Реклама", "type": "expense", "is_active": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


def test_operator_can_read_but_not_write_reference(client, db_session):
    operator = make_user(db_session, RoleEnum.operator)
    headers = auth_headers(operator)

    resp = client.get("/categories", headers=headers)
    assert resp.status_code == 200

    resp = client.post("/projects", headers=headers, json={"name": "x"})
    assert resp.status_code == 403
