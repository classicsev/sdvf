from datetime import date, timedelta

from app.models import RoleEnum, TxTypeEnum
from app.scheduler import generate_due_recurring
from tests.conftest import auth_headers, make_account, make_category, make_user


def test_recurring_template_crud(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, "Аренда", TxTypeEnum.expense)

    resp = client.post(
        "/recurring-templates",
        headers=headers,
        json={
            "type": "expense",
            "amount_rub": 50000,
            "category_id": category.id,
            "account_id": account.id,
            "frequency": "monthly",
            "day_of_month": 5,
            "next_run_date": "2026-09-05",
        },
    )
    assert resp.status_code == 200, resp.text
    template = resp.json()
    assert template["is_active"] is True

    resp = client.get("/recurring-templates", headers=headers)
    assert len(resp.json()) == 1

    resp = client.patch(
        f"/recurring-templates/{template['id']}",
        headers=headers,
        json={**{k: v for k, v in template.items() if k != "id"}, "is_active": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    resp = client.delete(f"/recurring-templates/{template['id']}", headers=headers)
    assert resp.status_code == 200
    assert client.get("/recurring-templates", headers=headers).json() == []


def test_generate_due_recurring_creates_transaction_and_advances_date(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, "Аренда", TxTypeEnum.expense)

    due_date = date.today() - timedelta(days=1)
    resp = client.post(
        "/recurring-templates",
        headers=headers,
        json={
            "type": "expense",
            "amount_rub": 30000,
            "category_id": category.id,
            "account_id": account.id,
            "frequency": "monthly",
            "day_of_month": due_date.day if due_date.day <= 28 else 28,
            "next_run_date": due_date.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    template_id = resp.json()["id"]

    created = generate_due_recurring(db_session)
    assert created == 1

    resp = client.get("/transactions", headers=headers)
    tx = next(t for t in resp.json() if t["comment"] is None and float(t["amount_rub"]) == 30000.0)
    assert tx["payment_confirmed"] is False
    assert tx["accrual_confirmed"] is False

    resp = client.get("/recurring-templates", headers=headers)
    updated = next(t for t in resp.json() if t["id"] == template_id)
    assert updated["next_run_date"] > due_date.isoformat()

    # Повторный вызов в тот же день не должен создавать вторую операцию —
    # next_run_date уже сдвинут на будущее
    created_again = generate_due_recurring(db_session)
    assert created_again == 0
