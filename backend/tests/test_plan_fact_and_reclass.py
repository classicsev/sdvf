"""План/факт (payment_confirmed/accrual_confirmed) + операции Перемещение
(/transactions/transfer) и Начисление (/transactions/reclass).
См. HANDOVER.md, "План/факт (ПланФакт-стиль)"."""

from app.models import RoleEnum, Transaction, TxTypeEnum
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


# ---------------------------------------------------------------------------
# payment_confirmed — влияет на остаток счёта
# ---------------------------------------------------------------------------


def test_unconfirmed_payment_excluded_from_account_balance(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=1000)
    category = make_category(db_session, tx_type=TxTypeEnum.expense)

    _create_tx(client, headers, account.id, category.id, 300, "expense", payment_confirmed=False)

    balances = client.get("/reports/account-balances", headers=headers).json()
    row = next(r for r in balances["accounts"] if r["id"] == account.id)
    assert row["balance"] == 1000.0


def test_confirming_payment_makes_it_count_toward_balance(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=1000)
    category = make_category(db_session, tx_type=TxTypeEnum.expense)

    tx = _create_tx(client, headers, account.id, category.id, 300, "expense", payment_confirmed=False)
    resp = client.patch(f"/transactions/{tx['id']}", headers=headers, json={"payment_confirmed": True})
    assert resp.status_code == 200, resp.text

    balances = client.get("/reports/account-balances", headers=headers).json()
    row = next(r for r in balances["accounts"] if r["id"] == account.id)
    assert row["balance"] == 700.0


# ---------------------------------------------------------------------------
# accrual_confirmed — влияет на П&Л-отчёты (dashboard/pnl/profitability/debt/
# платёжный календарь), но НЕ на остаток счёта
# ---------------------------------------------------------------------------


def test_unconfirmed_accrual_excluded_from_dashboard_period_income(client, db_session):
    from datetime import date

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=0)
    category = make_category(db_session, tx_type=TxTypeEnum.income)
    today = date.today().isoformat()

    # Деньги пришли (оплата подтверждена), но начисление — нет (например,
    # аванс за ещё не оказанную услугу): в остатке видно, в П&Л — нет.
    _create_tx(
        client, headers, account.id, category.id, 5000, "income",
        date_odds=today, payment_confirmed=True, accrual_confirmed=False,
    )

    balances = client.get("/reports/account-balances", headers=headers).json()
    assert balances["accounts"][0]["balance"] == 5000.0

    dashboard = client.get("/reports/dashboard-summary", headers=headers).json()
    assert dashboard["period_income_rub"] == 0.0


def test_confirmed_accrual_but_unconfirmed_payment_counts_in_pnl_not_balance(client, db_session):
    """Обратный случай: отгрузили (начисление подтверждено — это выручка),
    но ещё не оплатили (деньги подтверждены не были) — П&Л видит доход,
    остаток счёта — нет."""
    from datetime import date

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=0)
    category = make_category(db_session, tx_type=TxTypeEnum.income)
    today = date.today().isoformat()

    _create_tx(
        client, headers, account.id, category.id, 5000, "income",
        date_odds=today, payment_confirmed=False, accrual_confirmed=True,
    )

    balances = client.get("/reports/account-balances", headers=headers).json()
    assert balances["accounts"][0]["balance"] == 0.0

    dashboard = client.get("/reports/dashboard-summary", headers=headers).json()
    assert dashboard["period_income_rub"] == 5000.0


def test_debt_report_filters_by_accrual_not_payment(client, db_session):
    """debt_report — самая суть задолженности в том, что она НЕ оплачена,
    поэтому фильтр по accrual_confirmed (обязательство признано), а не по
    payment_confirmed (иначе весь неоплаченный долг исчез бы из отчёта)."""
    from tests.conftest import make_counterparty

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.expense)
    cp = make_counterparty(db_session, "Поставщик")

    _create_tx(
        client, headers, account.id, category.id, 1500, "expense",
        counterparty_id=cp.id, payment_confirmed=False, accrual_confirmed=True,
    )

    resp = client.get("/reports/debt", headers=headers)
    row = next(r for r in resp.json() if r["counterparty_id"] == cp.id)
    assert row["net_amount_rub"] == -1500.0


# ---------------------------------------------------------------------------
# Перемещение (/transactions/transfer) — план/факт по payment_confirmed
# ---------------------------------------------------------------------------


def test_planned_transfer_excluded_from_both_account_balances(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    from_account = make_account(db_session, name="Тбанк", opening_balance=1000)
    to_account = make_account(db_session, name="Наличные", opening_balance=0)

    resp = client.post(
        "/transactions/transfer",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "from_account_id": from_account.id,
            "to_account_id": to_account.id,
            "amount": 400,
            "payment_confirmed": False,
        },
    )
    assert resp.status_code == 200, resp.text

    balances = {r["id"]: r["balance"] for r in client.get("/reports/account-balances", headers=headers).json()["accounts"]}
    assert balances[from_account.id] == 1000.0
    assert balances[to_account.id] == 0.0


def test_confirmed_transfer_moves_balance_between_accounts(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    from_account = make_account(db_session, name="Тбанк", opening_balance=1000)
    to_account = make_account(db_session, name="Наличные", opening_balance=0)

    resp = client.post(
        "/transactions/transfer",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "from_account_id": from_account.id,
            "to_account_id": to_account.id,
            "amount": 400,
        },
    )
    assert resp.status_code == 200, resp.text

    balances = {r["id"]: r["balance"] for r in client.get("/reports/account-balances", headers=headers).json()["accounts"]}
    assert balances[from_account.id] == 600.0
    assert balances[to_account.id] == 400.0


def test_transfer_excluded_from_dashboard_income_expense(client, db_session):
    from datetime import date

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    from_account = make_account(db_session, name="Тбанк", opening_balance=1000)
    to_account = make_account(db_session, name="Наличные", opening_balance=0)
    today = date.today().isoformat()

    resp = client.post(
        "/transactions/transfer",
        headers=headers,
        json={"date_odds": today, "from_account_id": from_account.id, "to_account_id": to_account.id, "amount": 400},
    )
    assert resp.status_code == 200, resp.text

    dashboard = client.get("/reports/dashboard-summary", headers=headers).json()
    assert dashboard["period_income_rub"] == 0.0
    assert dashboard["period_expense_rub"] == 0.0


def test_delete_transfer_deletes_both_legs(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    from_account = make_account(db_session, name="Тбанк", opening_balance=1000)
    to_account = make_account(db_session, name="Наличные", opening_balance=0)

    created = client.post(
        "/transactions/transfer",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "from_account_id": from_account.id,
            "to_account_id": to_account.id,
            "amount": 400,
        },
    ).json()

    del_resp = client.delete(f"/transactions/{created['expense']['id']}", headers=headers)
    assert del_resp.status_code == 200, del_resp.text
    assert del_resp.json()["paired_deleted"] is True

    remaining = db_session.query(Transaction).filter(Transaction.id == created["income"]["id"]).first()
    assert remaining is None


def test_transfer_rejects_same_account(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=1000)

    resp = client.post(
        "/transactions/transfer",
        headers=headers,
        json={"date_odds": "2026-06-01", "from_account_id": account.id, "to_account_id": account.id, "amount": 100},
    )
    assert resp.status_code == 422


def test_transfer_rejects_currency_mismatch(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    rub_account = make_account(db_session, currency="RUB", opening_balance=1000)
    cny_account = make_account(db_session, currency="CNY", opening_balance=0)

    resp = client.post(
        "/transactions/transfer",
        headers=headers,
        json={"date_odds": "2026-06-01", "from_account_id": rub_account.id, "to_account_id": cny_account.id, "amount": 100},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Начисление (/transactions/reclass) — перенос суммы между статьями
# ---------------------------------------------------------------------------


def test_reclass_shifts_category_breakdown_without_changing_total_pnl(client, db_session):
    from datetime import date

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    cat_a = make_category(db_session, "Реклама", TxTypeEnum.expense)
    cat_b = make_category(db_session, "Реклама Facebook", TxTypeEnum.expense)
    today = date.today().isoformat()

    _create_tx(client, headers, account.id, cat_a.id, 1000, "expense", date_odds=today)

    resp = client.post(
        "/transactions/reclass",
        headers=headers,
        json={
            "date_odds": today,
            "account_id": account.id,
            "from_category_id": cat_a.id,
            "to_category_id": cat_b.id,
            "currency": "RUB",
            "amount": 1000,
        },
    )
    assert resp.status_code == 200, resp.text

    dashboard = client.get("/reports/dashboard-summary", headers=headers).json()
    assert dashboard["period_expense_rub"] == 1000.0  # общий П&Л не изменился

    pnl = client.get("/reports/pnl", params={"period": today[:7]}, headers=headers).json()
    groups = {row["group"]: row["amount"] for row in pnl["expenses"]}
    assert groups.get(cat_a.name, 0) == 0.0
    assert groups.get(cat_b.name, 0) == 1000.0


def test_reclass_rejects_cross_type_categories(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    income_cat = make_category(db_session, "Продажи", TxTypeEnum.income)
    expense_cat = make_category(db_session, "Реклама", TxTypeEnum.expense)

    resp = client.post(
        "/transactions/reclass",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "from_category_id": income_cat.id,
            "to_category_id": expense_cat.id,
            "currency": "RUB",
            "amount": 100,
        },
    )
    assert resp.status_code == 422


def test_reclass_rejects_same_category(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.expense)

    resp = client.post(
        "/transactions/reclass",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "from_category_id": category.id,
            "to_category_id": category.id,
            "currency": "RUB",
            "amount": 100,
        },
    )
    assert resp.status_code == 422


def test_delete_reclass_deletes_both_legs(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    cat_a = make_category(db_session, "Статья A", TxTypeEnum.expense)
    cat_b = make_category(db_session, "Статья Б", TxTypeEnum.expense)

    created = client.post(
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
    ).json()

    del_resp = client.delete(f"/transactions/{created['from_leg']['id']}", headers=headers)
    assert del_resp.status_code == 200, del_resp.text
    assert del_resp.json()["paired_deleted"] is True

    remaining = db_session.query(Transaction).filter(Transaction.id == created["to_leg"]["id"]).first()
    assert remaining is None
