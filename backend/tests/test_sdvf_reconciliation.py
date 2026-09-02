from datetime import date
from decimal import Decimal

from app.config import settings
from app.models import Counterparty, Transaction, TxTypeEnum
from tests.conftest import make_account, make_category, make_company, make_user


def _seed(db_session):
    company = make_company(db_session, "ООО Тест")
    company.sdvf_org_inn = "2500000000"
    user = make_user(db_session, company_id=company.id)
    counterparty = Counterparty(company_id=company.id, name="ООО Покупатель", inn="7300036917")
    db_session.add(counterparty)
    db_session.flush()
    account = make_account(db_session, company_id=company.id)
    category = make_category(db_session, tx_type=TxTypeEnum.income, company_id=company.id)
    db_session.add(
        Transaction(
            company_id=company.id,
            date_odds=date(2026, 2, 18),
            account_id=account.id,
            category_id=category.id,
            counterparty_id=counterparty.id,
            type=TxTypeEnum.income,
            amount=Decimal("28812.00"),
            amount_rub=Decimal("28812.00"),
            currency="RUB",
            bank_payment_purpose="Оплата по УПД ТД-176",
            external_ref="bank:test-1",
        )
    )
    db_session.commit()
    return user


def test_reconciliation_feed_is_scoped_and_returns_income(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "sdvf_reconciliation_api_key", "test-key")
    user = _seed(db_session)

    response = client.get(
        "/integration/sdvf/reconciliation-data",
        headers={"X-API-Key": "test-key"},
        params={
            "user_id": user.id,
            "organization_inn": "25 000 000 00",
            "counterparty_inn": "7300036917",
            "date_from": "2026-01-01",
            "date_to": "2026-09-02",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["organization"]["inn"] == "2500000000"
    assert payload["counterparty"]["inn"] == "7300036917"
    assert payload["items"] == [
        {
            "id": payload["items"][0]["id"],
            "date": "2026-02-18",
            "amount": 28812.0,
            "purpose": "Оплата по УПД ТД-176",
            "external_ref": "bank:test-1",
        }
    ]


def test_reconciliation_feed_rejects_wrong_key(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "sdvf_reconciliation_api_key", "test-key")
    user = _seed(db_session)
    response = client.get(
        "/integration/sdvf/reconciliation-data",
        headers={"X-API-Key": "wrong"},
        params={
            "user_id": user.id,
            "organization_inn": "2500000000",
            "counterparty_inn": "7300036917",
            "date_from": "2026-01-01",
            "date_to": "2026-09-02",
        },
    )
    assert response.status_code == 401


def test_reconciliation_feed_cannot_read_another_users_company(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "sdvf_reconciliation_api_key", "test-key")
    _seed(db_session)
    other_company = make_company(db_session, "Другая компания")
    other_user = make_user(db_session, company_id=other_company.id)

    response = client.get(
        "/integration/sdvf/reconciliation-data",
        headers={"X-API-Key": "test-key"},
        params={
            "user_id": other_user.id,
            "organization_inn": "2500000000",
            "counterparty_inn": "7300036917",
            "date_from": "2026-01-01",
            "date_to": "2026-09-02",
        },
    )
    assert response.status_code == 404
