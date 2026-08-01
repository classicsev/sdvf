from app.models import RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_counterparty, make_user


def _tx(client, headers, **kwargs):
    payload = {
        "date_odds": "2026-06-01",
        "currency": "RUB",
    }
    payload.update(kwargs)
    resp = client.post("/transactions", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_cashflow_by_month_when_no_period(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    income = make_category(db_session, "Приход", TxTypeEnum.income)
    expense = make_category(db_session, "Расход", TxTypeEnum.expense)

    _tx(client, headers, account_id=account.id, category_id=income.id, type="income", amount=1000, date_odds="2026-06-05")
    _tx(client, headers, account_id=account.id, category_id=expense.id, type="expense", amount=400, date_odds="2026-06-10")

    resp = client.get("/reports/cashflow", headers=headers)
    assert resp.status_code == 200
    month = next(m for m in resp.json()["by_month"] if m["period"] == "2026-06")
    assert month["income"] == 1000.0
    assert month["expense"] == 400.0
    assert month["net"] == 600.0


def test_cashflow_by_category_with_period(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, "Аренда", TxTypeEnum.expense)

    _tx(client, headers, account_id=account.id, category_id=category.id, type="expense", amount=5000, date_odds="2026-06-05")
    # операция в другом месяце не должна попасть в выборку
    _tx(client, headers, account_id=account.id, category_id=category.id, type="expense", amount=9999, date_odds="2026-07-05")

    resp = client.get("/reports/cashflow?period=2026-06", headers=headers)
    assert resp.status_code == 200
    row = next(r for r in resp.json()["by_category"] if r["category_id"] == category.id)
    assert row["expense"] == 5000.0


def test_balance_report_assets_and_staff_liability(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=10000)

    employee = client.post("/payroll/employees", headers=headers, json={"full_name": "Тест"}).json()
    client.post(
        "/payroll/accruals",
        headers=headers,
        json={"employee_id": employee["id"], "period": "2026-06-01", "salary": 8000},
    )
    client.post(
        "/payroll/payments",
        headers=headers,
        json={"employee_id": employee["id"], "account_id": account.id, "date": "2026-06-10", "amount": 3000},
    )

    resp = client.get("/reports/balance?as_of=2026-06-30", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["assets"]["cash_rub"] == 10000.0
    assert body["liabilities"]["payable_to_staff_rub"] == 5000.0  # 8000 начислено - 3000 выплачено
    assert body["retained_earnings_rub"] == 5000.0  # 10000 - 5000


def test_debt_report_nets_income_and_expense_per_counterparty(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    income = make_category(db_session, "Приход", TxTypeEnum.income)
    expense = make_category(db_session, "Расход", TxTypeEnum.expense)
    cp = make_counterparty(db_session, "ИП Мальшин")

    _tx(client, headers, account_id=account.id, category_id=income.id, type="income", amount=50000, counterparty_id=cp.id)
    _tx(client, headers, account_id=account.id, category_id=expense.id, type="expense", amount=30000, counterparty_id=cp.id)

    resp = client.get("/reports/debt", headers=headers)
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["counterparty_id"] == cp.id)
    assert row["net_amount_rub"] == 20000.0


def test_viewer_can_read_all_reports_readonly(client, db_session):
    viewer = make_user(db_session, RoleEnum.viewer)
    headers = auth_headers(viewer)
    for path in (
        "/reports/dashboard-summary",
        "/reports/cashflow",
        "/reports/pnl",
        "/reports/balance",
        "/reports/debt",
        "/reports/profitability",
        "/reports/payment-calendar",
    ):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"


def test_payroll_operator_has_no_reports_access(client, db_session):
    # По матрице прав в README: "Дашборд/отчёты" — payroll_operator = "нет".
    payroll_op = make_user(db_session, RoleEnum.payroll_operator)
    headers = auth_headers(payroll_op)
    for path in ("/reports/dashboard-summary", "/reports/cashflow", "/reports/payment-calendar"):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 403, f"{path} -> {resp.status_code}"
