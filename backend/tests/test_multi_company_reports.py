from datetime import date

from app.models import RoleEnum, Transaction, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_company, make_user


def _make_second_company(client, admin_headers, name="Компания Б"):
    resp = client.post("/companies", json={"name": name}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["company"]["id"]


def _seed_income(db_session, company_id, amount):
    account = make_account(db_session, company_id=company_id)
    category = make_category(db_session, tx_type=TxTypeEnum.income, company_id=company_id)
    tx = Transaction(
        company_id=company_id,
        date_odds=date.today().replace(day=1),
        account_id=account.id,
        category_id=category.id,
        type=TxTypeEnum.income,
        amount=amount,
        currency="RUB",
        amount_rub=amount,
    )
    db_session.add(tx)
    db_session.commit()
    return account


def test_cashflow_combines_all_companies_by_default(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    _seed_income(db_session, admin.company_id, 1000)
    _seed_income(db_session, company_b, 500)

    resp = client.get("/reports/cashflow", headers=headers)
    assert resp.status_code == 200, resp.text
    total_income = sum(row["income"] for row in resp.json()["by_month"])
    assert total_income == 1500.0


def test_cashflow_filtered_to_one_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    _seed_income(db_session, admin.company_id, 1000)
    _seed_income(db_session, company_b, 500)

    resp = client.get("/reports/cashflow", params={"company_id": company_b}, headers=headers)
    assert resp.status_code == 200, resp.text
    total_income = sum(row["income"] for row in resp.json()["by_month"])
    assert total_income == 500.0


def test_pnl_filtered_to_one_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    _seed_income(db_session, admin.company_id, 1000)
    _seed_income(db_session, company_b, 500)

    resp = client.get("/reports/pnl", params={"company_id": company_b}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["revenue"] == 500.0


def test_balance_combines_all_companies_by_default(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    make_account(db_session, opening_balance=1000, company_id=admin.company_id)
    make_account(db_session, opening_balance=500, company_id=company_b)

    resp = client.get("/reports/balance", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["assets"]["cash_rub"] == 1500.0


def test_balance_filtered_to_one_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    make_account(db_session, opening_balance=1000, company_id=admin.company_id)
    make_account(db_session, opening_balance=500, company_id=company_b)

    resp = client.get("/reports/balance", params={"company_id": company_b}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["assets"]["cash_rub"] == 500.0


def test_payment_calendar_filtered_to_one_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    _seed_income(db_session, admin.company_id, 1000)
    _seed_income(db_session, company_b, 500)

    resp = client.get("/reports/payment-calendar", params={"company_id": company_b}, headers=headers)
    assert resp.status_code == 200, resp.text
    total_fact = sum(q["fact"] for row in resp.json()["rows"] for q in row["quarters"])
    assert total_fact == 500.0


def test_reports_reject_company_id_without_access(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other_company = make_company(db_session, name="Чужая компания")
    other_admin = make_user(db_session, RoleEnum.admin, company_id=other_company.id)

    for path in ("/reports/cashflow", "/reports/pnl", "/reports/balance", "/reports/debt", "/reports/profitability"):
        resp = client.get(path, params={"company_id": other_admin.company_id}, headers=auth_headers(admin))
        assert resp.status_code == 404, f"{path}: {resp.text}"
