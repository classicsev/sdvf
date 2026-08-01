from app.models import RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_user


def test_admin_sees_all_audit_entries(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.income)
    employee = client.post("/payroll/employees", headers=headers, json={"full_name": "Тест"}).json()

    client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 100,
            "currency": "RUB",
        },
    )
    client.post(
        "/payroll/accruals",
        headers=headers,
        json={"employee_id": employee["id"], "period": "2026-06-01", "salary": 1000},
    )

    resp = client.get("/audit-log", headers=headers)
    assert resp.status_code == 200
    entity_types = {e["entity_type"] for e in resp.json()}
    assert "transaction" in entity_types
    assert "payroll_accrual" in entity_types


def test_payroll_operator_sees_only_payroll_entries(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    payroll_op = make_user(db_session, RoleEnum.payroll_operator)
    admin_headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.income)
    employee = client.post("/payroll/employees", headers=admin_headers, json={"full_name": "Тест"}).json()

    client.post(
        "/transactions",
        headers=admin_headers,
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 100,
            "currency": "RUB",
        },
    )
    client.post(
        "/payroll/accruals",
        headers=admin_headers,
        json={"employee_id": employee["id"], "period": "2026-06-01", "salary": 1000},
    )

    resp = client.get("/audit-log", headers=auth_headers(payroll_op))
    assert resp.status_code == 200
    entity_types = {e["entity_type"] for e in resp.json()}
    assert entity_types <= {"payroll_accrual", "payroll_payment"}
    assert "transaction" not in entity_types
    assert len(resp.json()) > 0  # начисление всё же должно быть видно


def test_operator_has_no_audit_access(client, db_session):
    operator = make_user(db_session, RoleEnum.operator)
    resp = client.get("/audit-log", headers=auth_headers(operator))
    assert resp.status_code == 403
