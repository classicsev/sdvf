from datetime import date

from app.models import Account, RoleEnum, Transaction, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_user


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


def test_dashboard_combines_all_companies_by_default(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    _seed_income(db_session, admin.company_id, 1000)
    _seed_income(db_session, company_b, 500)

    resp = client.get("/reports/dashboard-summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["period_income_rub"] == 1500.0

    by_company = {row["company_id"]: row for row in body["by_company"]}
    assert by_company[admin.company_id]["period_income_rub"] == 1000.0
    assert by_company[company_b]["period_income_rub"] == 500.0


def test_dashboard_filtered_to_one_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    _seed_income(db_session, admin.company_id, 1000)
    _seed_income(db_session, company_b, 500)

    resp = client.get("/reports/dashboard-summary", params={"company_id": company_b}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["period_income_rub"] == 500.0
    assert len(body["by_company"]) == 1
    assert body["by_company"][0]["company_id"] == company_b
