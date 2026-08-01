from app.models import RoleEnum
from tests.conftest import auth_headers, make_account, make_user


def test_employee_bank_details_roundtrip_and_not_stored_plaintext(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)

    resp = client.post(
        "/payroll/employees",
        headers=auth_headers(admin),
        json={"full_name": "Тест Тестов", "bank_details": "Т-Банк, счёт 40817..."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bank_details"] == "Т-Банк, счёт 40817..."

    from app.models import Employee

    raw = db_session.get(Employee, body["id"])
    assert raw.bank_details_encrypted is not None
    assert "40817" not in raw.bank_details_encrypted


def test_accrual_total_is_server_computed_not_trusted(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    employee = client.post(
        "/payroll/employees", headers=auth_headers(admin), json={"full_name": "Иванов И.И."}
    ).json()

    resp = client.post(
        "/payroll/accruals",
        headers=auth_headers(admin),
        json={
            "employee_id": employee["id"],
            "period": "2026-06-01",
            "salary": 80000,
            "bonus": 5000,
            "deductions": 1000,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 84000.0


def test_operator_has_no_payroll_access(client, db_session):
    operator = make_user(db_session, RoleEnum.operator)
    resp = client.get("/payroll/employees", headers=auth_headers(operator))
    assert resp.status_code == 403


def test_payroll_summary_excludes_names(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer)
    employee = client.post(
        "/payroll/employees", headers=auth_headers(admin), json={"full_name": "Секретный Сотрудников"}
    ).json()
    client.post(
        "/payroll/accruals",
        headers=auth_headers(admin),
        json={"employee_id": employee["id"], "period": "2026-06-01", "salary": 10000},
    )

    resp = client.get("/payroll/summary-for-viewer", headers=auth_headers(viewer))
    assert resp.status_code == 200
    assert "Секретный" not in resp.text
    assert resp.json()["total_accrued"] == 10000.0


def test_malformed_uuid_on_employee_returns_404(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.patch(
        "/payroll/employees/not-a-uuid", headers=auth_headers(admin), json={"full_name": "x"}
    )
    assert resp.status_code == 404

    resp = client.delete("/payroll/employees/not-a-uuid", headers=auth_headers(admin))
    assert resp.status_code == 404


def test_payment_requires_existing_accrual(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session)
    employee = client.post(
        "/payroll/employees", headers=auth_headers(admin), json={"full_name": "Петров П.П."}
    ).json()

    resp = client.post(
        "/payroll/payments",
        headers=auth_headers(admin),
        json={
            "employee_id": employee["id"],
            "accrual_id": "00000000-0000-0000-0000-000000000000",
            "account_id": account.id,
            "date": "2026-06-01",
            "amount": 1000,
        },
    )
    assert resp.status_code == 404


def test_employee_list_update_delete(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    employee = client.post(
        "/payroll/employees",
        headers=headers,
        json={"full_name": "Сидоров С.С.", "department": "Отдел продаж", "employment_type": "ИП"},
    ).json()

    resp = client.get("/payroll/employees", headers=headers)
    assert any(e["id"] == employee["id"] for e in resp.json())

    resp = client.patch(
        f"/payroll/employees/{employee['id']}",
        headers=headers,
        json={"full_name": "Сидоров С.С.", "department": "Отдел маркетинга"},
    )
    assert resp.status_code == 200
    assert resp.json()["department"] == "Отдел маркетинга"

    resp = client.delete(f"/payroll/employees/{employee['id']}", headers=headers)
    assert resp.status_code == 200

    resp = client.get("/payroll/employees", headers=headers)
    assert not any(e["id"] == employee["id"] for e in resp.json())


def test_accruals_filtered_by_period(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    employee = client.post("/payroll/employees", headers=headers, json={"full_name": "Тест"}).json()

    client.post(
        "/payroll/accruals",
        headers=headers,
        json={"employee_id": employee["id"], "period": "2026-06-01", "salary": 1000},
    )
    client.post(
        "/payroll/accruals",
        headers=headers,
        json={"employee_id": employee["id"], "period": "2026-07-01", "salary": 2000},
    )

    resp = client.get("/payroll/accruals?period=2026-06", headers=headers)
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["salary"] == 1000.0

    resp = client.get("/payroll/accruals", headers=headers)
    assert len(resp.json()) == 2


def test_payments_list(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    employee = client.post("/payroll/employees", headers=headers, json={"full_name": "Тест"}).json()

    client.post(
        "/payroll/payments",
        headers=headers,
        json={"employee_id": employee["id"], "account_id": account.id, "date": "2026-06-05", "amount": 5000},
    )

    resp = client.get("/payroll/payments", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["amount"] == 5000.0
