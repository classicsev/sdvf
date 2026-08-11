from app.models import RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_project, make_user


def test_planning_crud_and_role_restriction(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer)
    category = make_category(db_session, "Аренда", TxTypeEnum.expense)

    resp = client.post(
        "/planning",
        headers=auth_headers(viewer),
        json={"category_id": category.id, "amount": 1000, "scheduled_date": "2026-07-01"},
    )
    assert resp.status_code == 403

    resp = client.post(
        "/planning",
        headers=auth_headers(admin),
        json={"category_id": category.id, "amount": 50000, "frequency": "monthly", "scheduled_date": "2026-07-01"},
    )
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]

    resp = client.patch(
        f"/planning/{plan_id}",
        headers=auth_headers(admin),
        json={"category_id": category.id, "amount": 60000, "frequency": "monthly", "scheduled_date": "2026-07-01"},
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == 60000.0

    resp = client.delete(f"/planning/{plan_id}", headers=auth_headers(admin))
    assert resp.status_code == 200

    resp = client.get("/planning?year=2026", headers=auth_headers(admin))
    assert resp.json() == []


def test_planning_feeds_payment_calendar_report(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, "Налоги", TxTypeEnum.expense)

    client.post(
        "/planning",
        headers=headers,
        json={"category_id": category.id, "amount": 12000, "frequency": "monthly", "scheduled_date": "2026-02-10"},
    )
    client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": "2026-02-15",
            "account_id": account.id,
            "category_id": category.id,
            "type": "expense",
            "amount": 11500,
            "currency": "RUB",
        },
    )

    resp = client.get("/reports/payment-calendar?quarter=2026", headers=headers)
    assert resp.status_code == 200
    row = next(r for r in resp.json()["rows"] if r["category_id"] == category.id)
    q1 = next(q for q in row["quarters"] if q["quarter"] == 1)
    assert q1["plan"] == 12000.0
    assert q1["fact"] == -11500.0
    assert q1["deviation"] == -23500.0  # fact - plan


def test_create_planning_rejects_category_from_other_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    resp = client.post("/companies", json={"name": "Компания Б"}, headers=headers)
    assert resp.status_code == 201, resp.text
    company_b = resp.json()["company"]["id"]

    # Статья принадлежит основной компании admin, а не company_b.
    category = make_category(db_session, "Аренда", TxTypeEnum.expense, company_id=admin.company_id)

    resp = client.post(
        "/planning",
        params={"company_id": company_b},
        headers=headers,
        json={"category_id": category.id, "amount": 1000, "scheduled_date": "2026-07-01"},
    )
    assert resp.status_code == 404


def test_malformed_uuid_on_planning_returns_404(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.patch(
        "/planning/not-a-uuid",
        headers=auth_headers(admin),
        json={"category_id": "x", "amount": 1, "scheduled_date": "2026-01-01"},
    )
    assert resp.status_code == 404
