from app.models import RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_user


def _create_tx(client, headers, account_id, category_id, amount, tx_type, date_odds="2026-06-15", **extra):
    payload = {
        "date_odds": date_odds,
        "account_id": account_id,
        "category_id": category_id,
        "type": tx_type,
        "amount": amount,
        "currency": "RUB",
    }
    payload.update(extra)
    resp = client.post("/transactions", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_dashboard_summary_balance_matches_opening_plus_flow(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=1000)
    income_cat = make_category(db_session, "Приход", TxTypeEnum.income)
    expense_cat = make_category(db_session, "Расход", TxTypeEnum.expense)

    _create_tx(client, headers, account.id, income_cat.id, 500, "income")
    _create_tx(client, headers, account.id, expense_cat.id, 200, "expense")

    resp = client.get("/reports/dashboard-summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    acc = next(a for a in body["accounts"] if a["id"] == account.id)
    assert acc["balance"] == 1300.0  # 1000 + 500 - 200


def test_dashboard_summary_excludes_financing_category_from_income_expense(client, db_session):
    # Кредитная линия/овердрафт (Category.is_financing) не должна попадать в
    # "Приход/Расход" — реальный кейс, обнаруженный на живых данных Т-Банка
    # (см. integrations/tbank.py::FINANCING_CATEGORIES), но должна оставаться
    # в остатке счёта — деньги реально прошли по счёту.
    # dashboard-summary всегда берёт текущий месяц по date.today() (в отличие
    # от pnl/cashflow), поэтому дата операций — динамическая "сегодня", не
    # захардкоженная, чтобы тест не был завязан на месяц запуска.
    from datetime import date as _date

    today = _date.today().isoformat()

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=1000)
    income_cat = make_category(db_session, "Приход", TxTypeEnum.income)
    expense_cat = make_category(db_session, "Расход", TxTypeEnum.expense)
    loan_draw_cat = make_category(db_session, "Кредитная линия: пополнение", TxTypeEnum.income, is_financing=True)
    loan_repay_cat = make_category(db_session, "Кредитная линия: погашение", TxTypeEnum.expense, is_financing=True)

    _create_tx(client, headers, account.id, income_cat.id, 500, "income", date_odds=today)
    _create_tx(client, headers, account.id, expense_cat.id, 200, "expense", date_odds=today)
    _create_tx(client, headers, account.id, loan_draw_cat.id, 50000, "income", date_odds=today)
    _create_tx(client, headers, account.id, loan_repay_cat.id, 50000, "expense", date_odds=today)

    resp = client.get("/reports/dashboard-summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["period_income_rub"] == 500.0
    assert body["period_expense_rub"] == 200.0
    # Остаток счёта включает и кредитную линию — она реально прошла по счёту
    acc = next(a for a in body["accounts"] if a["id"] == account.id)
    assert acc["balance"] == 1300.0  # 1000 + 500 - 200 + 50000 - 50000


def test_pnl_report_excludes_financing_category(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    income_cat = make_category(db_session, "Продажи", TxTypeEnum.income, group_name="Выручка")
    expense_cat = make_category(db_session, "Аренда", TxTypeEnum.expense, group_name="OPEX")
    loan_draw_cat = make_category(db_session, "Кредитная линия: пополнение", TxTypeEnum.income, is_financing=True)
    loan_repay_cat = make_category(db_session, "Кредитная линия: погашение", TxTypeEnum.expense, is_financing=True)

    _create_tx(client, headers, account.id, income_cat.id, 10000, "income")
    _create_tx(client, headers, account.id, expense_cat.id, 3000, "expense")
    _create_tx(client, headers, account.id, loan_draw_cat.id, 50000, "income")
    _create_tx(client, headers, account.id, loan_repay_cat.id, 50000, "expense")

    resp = client.get("/reports/pnl", headers=headers, params={"period": "2026-06"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["revenue"] == 10000.0
    assert body["total_expense"] == 3000.0
    assert all(row["group"] != "Финансовая деятельность" for row in body["expenses"])


def test_profitability_report_computes_margin(client, db_session):
    from tests.conftest import make_project

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    project = make_project(db_session)
    income_cat = make_category(db_session, "Приход", TxTypeEnum.income)
    expense_cat = make_category(db_session, "Расход", TxTypeEnum.expense)

    _create_tx(client, headers, account.id, income_cat.id, 1000, "income", project_id=project.id)
    _create_tx(client, headers, account.id, expense_cat.id, 400, "expense", project_id=project.id)

    resp = client.get("/reports/profitability", headers=headers)
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["project_id"] == project.id)
    assert row["revenue"] == 1000.0
    assert row["expense"] == 400.0
    assert row["profit"] == 600.0
    assert row["margin"] == 0.6


def test_project_manager_scoped_out_of_profitability_for_other_projects(client, db_session):
    from tests.conftest import make_project

    admin = make_user(db_session, RoleEnum.admin)
    project_a = make_project(db_session, "A")
    project_b = make_project(db_session, "B")
    pm = make_user(db_session, RoleEnum.project_manager, project_id=project_a.id)
    account = make_account(db_session)
    income_cat = make_category(db_session, "Приход", TxTypeEnum.income)

    _create_tx(client, auth_headers(admin), account.id, income_cat.id, 100, "income", project_id=project_a.id)
    _create_tx(client, auth_headers(admin), account.id, income_cat.id, 999999, "income", project_id=project_b.id)

    resp = client.get("/reports/profitability", headers=auth_headers(pm))
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["project_id"] == project_a.id


def test_pnl_report_groups_expenses_by_group_name(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    income_cat = make_category(db_session, "Продажи", TxTypeEnum.income, group_name="Выручка")
    expense_cat = make_category(db_session, "Аренда", TxTypeEnum.expense, group_name="OPEX")

    today = "2026-06-10"
    _create_tx(client, headers, account.id, income_cat.id, 5000, "income", date_odds=today)
    _create_tx(client, headers, account.id, expense_cat.id, 2000, "expense", date_odds=today)

    resp = client.get("/reports/pnl?period=2026-06", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["revenue"] == 5000.0
    assert body["total_expense"] == 2000.0
    assert body["net_profit"] == 3000.0
    assert {"group": "OPEX", "amount": 2000.0} in body["expenses"]
