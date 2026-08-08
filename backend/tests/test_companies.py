from app.models import RoleEnum
from tests.conftest import (
    auth_headers,
    make_account,
    make_category,
    make_company,
    make_counterparty,
    make_user,
)


# ---------------------------------------------------------------------------
# Регистрация новой компании
# ---------------------------------------------------------------------------


def test_register_company_happy_path(client, db_session):
    resp = client.post(
        "/auth/register-company",
        json={
            "company_name": "Ромашка ООО",
            "admin_email": "owner@romashka.local",
            "admin_full_name": "Иван Петров",
            "admin_password": "verystrongpass",
            "pdn_consent": True,
        },
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "owner@romashka.local"
    assert body["role"] == "admin"
    assert body["company"]["name"] == "Ромашка ООО"
    # Минимум по умолчанию: только Учёт, Склад выключен
    assert body["company"]["module_finance_enabled"] is True
    assert body["company"]["module_warehouse_enabled"] is False


def test_register_company_without_consent_rejected(client, db_session):
    resp = client.post(
        "/auth/register-company",
        json={
            "company_name": "Ромашка ООО",
            "admin_email": "owner2@romashka.local",
            "admin_full_name": "Иван Петров",
            "admin_password": "verystrongpass",
            "pdn_consent": False,
        },
    )
    assert resp.status_code == 400


def test_register_company_duplicate_email_rejected(client, db_session):
    make_user(db_session, RoleEnum.admin, email="taken@test.local")

    resp = client.post(
        "/auth/register-company",
        json={
            "company_name": "Другая компания",
            "admin_email": "taken@test.local",
            "admin_full_name": "Кто-то",
            "admin_password": "verystrongpass",
            "pdn_consent": True,
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Модули компании
# ---------------------------------------------------------------------------


def test_get_my_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.get("/companies/me", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json()["id"] == admin.company_id


def test_update_modules_requires_admin(client, db_session):
    viewer = make_user(db_session, RoleEnum.viewer)
    resp = client.patch(
        "/companies/me/modules", json={"module_warehouse_enabled": True}, headers=auth_headers(viewer)
    )
    assert resp.status_code == 403


def test_update_modules_round_trip_does_not_lose_data(client, db_session, _default_company):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session)
    category = make_category(db_session)

    tx = client.post(
        "/transactions",
        headers=auth_headers(admin),
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 100,
            "currency": "RUB",
        },
    )
    assert tx.status_code == 200
    tx_id = tx.json()["id"]

    # Выключаем Учёт
    off = client.patch(
        "/companies/me/modules", json={"module_finance_enabled": False}, headers=auth_headers(admin)
    )
    assert off.status_code == 200
    assert off.json()["module_finance_enabled"] is False

    blocked = client.get("/transactions", headers=auth_headers(admin))
    assert blocked.status_code == 403

    # Включаем обратно — данные должны быть на месте
    on = client.patch("/companies/me/modules", json={"module_finance_enabled": True}, headers=auth_headers(admin))
    assert on.status_code == 200

    restored = client.get("/transactions", headers=auth_headers(admin))
    assert restored.status_code == 200
    assert any(t["id"] == tx_id for t in restored.json())


# ---------------------------------------------------------------------------
# Изоляция между компаниями
# ---------------------------------------------------------------------------


def test_transactions_isolated_between_companies(client, db_session):
    company_a = make_company(db_session, name="Компания A")
    company_b = make_company(db_session, name="Компания B")

    admin_a = make_user(db_session, RoleEnum.admin, company_id=company_a.id)
    admin_b = make_user(db_session, RoleEnum.admin, company_id=company_b.id)

    account_a = make_account(db_session, name="Счёт A", company_id=company_a.id)
    category_a = make_category(db_session, name="Статья A", company_id=company_a.id)

    tx = client.post(
        "/transactions",
        headers=auth_headers(admin_a),
        json={
            "date_odds": "2026-06-01",
            "account_id": account_a.id,
            "category_id": category_a.id,
            "type": "income",
            "amount": 500,
            "currency": "RUB",
        },
    )
    assert tx.status_code == 200
    tx_id = tx.json()["id"]

    # Компания B не видит операцию компании A в списке
    list_b = client.get("/transactions", headers=auth_headers(admin_b))
    assert list_b.status_code == 200
    assert list_b.json() == []

    # Компания B не может достучаться до записи компании A напрямую — 404, а не чужие данные
    detail_b = client.patch(
        f"/transactions/{tx_id}", headers=auth_headers(admin_b), json={"comment": "hacked"}
    )
    assert detail_b.status_code == 404

    delete_b = client.delete(f"/transactions/{tx_id}", headers=auth_headers(admin_b))
    assert delete_b.status_code == 404

    # Справочники компании A тоже не видны компании B
    accounts_b = client.get("/accounts", headers=auth_headers(admin_b))
    assert accounts_b.json() == []
    accounts_a = client.get("/accounts", headers=auth_headers(admin_a))
    assert len(accounts_a.json()) == 1


def test_warehouse_isolated_between_companies(client, db_session):
    company_a = make_company(db_session, name="Компания A", module_warehouse=True)
    company_b = make_company(db_session, name="Компания B", module_warehouse=True)
    admin_a = make_user(db_session, RoleEnum.admin, company_id=company_a.id)
    admin_b = make_user(db_session, RoleEnum.admin, company_id=company_b.id)

    wh = client.post("/warehouse/warehouses", headers=auth_headers(admin_a), json={"name": "Склад A"})
    assert wh.status_code == 200
    wh_id = wh.json()["id"]

    list_b = client.get("/warehouse/warehouses", headers=auth_headers(admin_b))
    assert list_b.json() == []

    update_b = client.patch(
        f"/warehouse/warehouses/{wh_id}", headers=auth_headers(admin_b), json={"name": "Захват", "is_active": True}
    )
    assert update_b.status_code == 404


def test_counterparties_shared_between_finance_and_warehouse_modules(client, db_session):
    company = make_company(db_session, name="Обе функции", module_finance=True, module_warehouse=True)
    admin = make_user(db_session, RoleEnum.admin, company_id=company.id)
    make_counterparty(db_session, name="Общий клиент", company_id=company.id)

    resp = client.get("/counterparties", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Модуль-гейты
# ---------------------------------------------------------------------------


def test_warehouse_module_disabled_returns_403(client, db_session):
    company = make_company(db_session, name="Без склада", module_finance=True, module_warehouse=False)
    admin = make_user(db_session, RoleEnum.admin, company_id=company.id)

    resp = client.get("/warehouse/warehouses", headers=auth_headers(admin))
    assert resp.status_code == 403

    resp2 = client.get("/orders", headers=auth_headers(admin))
    assert resp2.status_code == 403

    resp3 = client.get("/production/recipes", headers=auth_headers(admin))
    assert resp3.status_code == 403


def test_finance_module_disabled_returns_403(client, db_session):
    company = make_company(db_session, name="Без учёта", module_finance=False, module_warehouse=True)
    admin = make_user(db_session, RoleEnum.admin, company_id=company.id)

    resp = client.get("/transactions", headers=auth_headers(admin))
    assert resp.status_code == 403

    resp2 = client.get("/categories", headers=auth_headers(admin))
    assert resp2.status_code == 403

    resp3 = client.get("/payroll/employees", headers=auth_headers(admin))
    assert resp3.status_code == 403


def test_warehouse_only_company_can_still_reach_counterparties(client, db_session):
    company = make_company(db_session, name="Только склад", module_finance=False, module_warehouse=True)
    admin = make_user(db_session, RoleEnum.admin, company_id=company.id)

    resp = client.get("/counterparties", headers=auth_headers(admin))
    assert resp.status_code == 200


def test_modules_page_reachable_even_when_module_disabled(client, db_session):
    company = make_company(db_session, name="Заблокированная", module_finance=False, module_warehouse=False)
    admin = make_user(db_session, RoleEnum.admin, company_id=company.id)

    resp = client.get("/companies/me", headers=auth_headers(admin))
    assert resp.status_code == 200

    turn_on = client.patch(
        "/companies/me/modules", json={"module_finance_enabled": True}, headers=auth_headers(admin)
    )
    assert turn_on.status_code == 200
    assert turn_on.json()["module_finance_enabled"] is True
