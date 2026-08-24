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


# ---------------------------------------------------------------------------
# Переключатель периода + сравнение с прошлым периодом на дашборде
# ---------------------------------------------------------------------------


def test_dashboard_summary_month_range_compares_to_previous_calendar_month(client, db_session, monkeypatch):
    import datetime as _dt

    class _FrozenDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 15)

    monkeypatch.setattr("app.routers.reports.date", _FrozenDate)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    income_cat = make_category(db_session, "Доход", TxTypeEnum.income)

    _create_tx(client, headers, account.id, income_cat.id, 1000, "income", date_odds="2026-03-10")  # текущий месяц
    _create_tx(client, headers, account.id, income_cat.id, 600, "income", date_odds="2026-02-10")  # прошлый месяц

    resp = client.get("/reports/dashboard-summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["range"] == "month"
    assert body["period_from"] == "2026-03-01"
    assert body["period_to"] == "2026-03-31"
    assert body["period_income_rub"] == 1000.0
    assert body["prev_period_from"] == "2026-02-01"
    assert body["prev_period_to"] == "2026-02-28"
    assert body["prev_period_income_rub"] == 600.0


def test_dashboard_summary_quarter_and_year_ranges(client, db_session, monkeypatch):
    import datetime as _dt

    class _FrozenDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 1)  # Q2 2026

    monkeypatch.setattr("app.routers.reports.date", _FrozenDate)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.get("/reports/dashboard-summary", params={"range": "quarter"}, headers=headers)
    body = resp.json()
    assert body["period_from"] == "2026-04-01"
    assert body["period_to"] == "2026-06-30"
    assert body["prev_period_from"] == "2026-01-01"
    assert body["prev_period_to"] == "2026-03-31"

    resp = client.get("/reports/dashboard-summary", params={"range": "year"}, headers=headers)
    body = resp.json()
    assert body["period_from"] == "2026-01-01"
    assert body["period_to"] == "2026-12-31"
    assert body["prev_period_from"] == "2025-01-01"
    assert body["prev_period_to"] == "2025-12-31"


def test_dashboard_summary_custom_range(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    income_cat = make_category(db_session, "Доход", TxTypeEnum.income)
    _create_tx(client, headers, account.id, income_cat.id, 777, "income", date_odds="2026-04-20")

    resp = client.get(
        "/reports/dashboard-summary",
        params={"date_from": "2026-04-01", "date_to": "2026-04-30"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["range"] == "custom"
    assert body["period_income_rub"] == 777.0
    # свой период "назад той же длины"
    assert body["prev_period_from"] == "2026-03-02"
    assert body["prev_period_to"] == "2026-03-31"


def test_dashboard_summary_defaults_to_month_on_invalid_range(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.get("/reports/dashboard-summary", params={"range": "decade"}, headers=auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json()["range"] == "month"


# ---------------------------------------------------------------------------
# Прогноз остатка (cashflow-forecast) — аналог короткого прогноза Xero на
# данных Планирования
# ---------------------------------------------------------------------------


def test_forecast_starts_from_current_balance(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    make_account(db_session, opening_balance=1000)

    resp = client.get("/reports/cashflow-forecast", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_balance_rub"] == 1000.0
    assert body["series"][0]["projected_balance_rub"] == 1000.0


def test_forecast_applies_unconfirmed_transactions(client, db_session):
    """cashflow-forecast теперь берёт "план" напрямую из операций с
    payment_confirmed=False (см. HANDOVER.md, "План/факт (ПланФакт-стиль)")
    — раньше источником была отдельная сущность Планирования."""
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=1000)
    income_cat = make_category(db_session, "План доход", TxTypeEnum.income)
    expense_cat = make_category(db_session, "План расход", TxTypeEnum.expense)

    from datetime import date, timedelta

    today = date.today()
    future_income_date = today + timedelta(days=5)
    future_expense_date = today + timedelta(days=2)

    _create_tx(
        client, headers, account.id, income_cat.id, 5000, "income",
        date_odds=future_income_date.isoformat(), payment_confirmed=False,
    )
    _create_tx(
        client, headers, account.id, expense_cat.id, 100, "expense",
        date_odds=future_expense_date.isoformat(), payment_confirmed=False,
    )
    # Уже подтверждённая будущая операция — НЕ должна попасть в "план" (она
    # уже факт, просто с датой в будущем).
    _create_tx(
        client, headers, account.id, expense_cat.id, 999, "expense",
        date_odds=future_expense_date.isoformat(), payment_confirmed=True,
    )

    resp = client.get("/reports/cashflow-forecast", params={"days": 30}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    by_date = {row["date"]: row for row in body["series"]}
    assert by_date[future_income_date.isoformat()]["planned_flow_rub"] == 5000.0
    assert by_date[future_expense_date.isoformat()]["planned_flow_rub"] == -100.0
    assert body["projected_balance_rub"] == 1000.0 + 5000.0 - 100.0


def test_reclass_legs_excluded_from_account_balance(client, db_session):
    """Ноги "Начисления" (reclass_pair_id) — всегда payment_confirmed=True
    (мгновенная корректировка, не план), поэтому исключаются из остатка
    отдельным фильтром reclass_pair_id.is_(None), а не через payment_confirmed."""
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=1000)
    cat_a = make_category(db_session, "Статья A", TxTypeEnum.expense)
    cat_b = make_category(db_session, "Статья Б", TxTypeEnum.expense)

    resp = client.post(
        "/transactions/reclass",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "from_category_id": cat_a.id,
            "to_category_id": cat_b.id,
            "currency": "RUB",
            "amount": 500,
        },
    )
    assert resp.status_code == 200, resp.text

    balances = client.get("/reports/account-balances", headers=headers).json()
    row = next(r for r in balances["accounts"] if r["id"] == account.id)
    assert row["balance"] == 1000.0
