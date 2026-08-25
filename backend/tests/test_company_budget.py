from app.models import RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_user


def test_admin_can_set_and_read_budget_lines(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    category = make_category(db_session, "Аренда", TxTypeEnum.expense)

    resp = client.post(
        "/company-budget-lines",
        headers=headers,
        params={"period": "2026-08"},
        json=[{"category_id": category.id, "amount": 100000}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["amount"] == 100000.0

    resp = client.get("/company-budget-lines", headers=headers, params={"period": "2026-08"})
    assert len(resp.json()) == 1


def test_replace_budget_lines_removes_missing_categories(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    cat_a = make_category(db_session, "Статья A", TxTypeEnum.expense)
    cat_b = make_category(db_session, "Статья Б", TxTypeEnum.expense)

    client.post(
        "/company-budget-lines",
        headers=headers,
        params={"period": "2026-08"},
        json=[{"category_id": cat_a.id, "amount": 1000}, {"category_id": cat_b.id, "amount": 2000}],
    )
    # Второй вызов без cat_b — должна пропасть
    client.post(
        "/company-budget-lines",
        headers=headers,
        params={"period": "2026-08"},
        json=[{"category_id": cat_a.id, "amount": 1500}],
    )
    resp = client.get("/company-budget-lines", headers=headers, params={"period": "2026-08"}).json()
    assert len(resp) == 1
    assert resp[0]["category_id"] == cat_a.id
    assert resp[0]["amount"] == 1500.0


def test_operator_cannot_set_budget_lines(client, db_session):
    operator = make_user(db_session, RoleEnum.operator)
    headers = auth_headers(operator)
    category = make_category(db_session)

    resp = client.post(
        "/company-budget-lines",
        headers=headers,
        params={"period": "2026-08"},
        json=[{"category_id": category.id, "amount": 100}],
    )
    assert resp.status_code == 403


def test_company_budget_report_plan_vs_fact(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, "Аренда", TxTypeEnum.expense)

    client.post(
        "/company-budget-lines",
        headers=headers,
        params={"period": "2026-08"},
        json=[{"category_id": category.id, "amount": 50000}],
    )
    client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": "2026-08-10",
            "account_id": account.id,
            "category_id": category.id,
            "type": "expense",
            "amount": 30000,
            "currency": "RUB",
        },
    )

    resp = client.get("/reports/company-budget", headers=headers, params={"period": "2026-08"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    line = next(l for l in body["lines"] if l["category_id"] == category.id)
    assert line["plan_rub"] == 50000.0
    assert line["fact_rub"] == 30000.0
    assert body["plan_total_rub"] == 50000.0
    assert body["fact_total_rub"] == 30000.0
