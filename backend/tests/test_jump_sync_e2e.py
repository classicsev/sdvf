"""E2E для Jump.Finance: подключение через общий /connect (простой токен, как
у Т-Банка), ручной /sync-jump, и автозапуск сопоставления после каждого
синка Т-Банка (по прямой просьбе пользователя)."""

from app.models import Integration, RoleEnum, Transaction
from app.routers import automation as automation_router
from tests.conftest import auth_headers, make_account, make_user


class _FakeTBankClient:
    def __init__(self, base_url, token):
        pass

    def fetch_all_operations(self, account_number, date_from, date_to=None):
        return iter(
            [
                {
                    "operationId": "op-1",
                    "typeOfOperation": "Debit",
                    "accountAmount": 5000.00,
                    "operationDate": "2026-06-01T00:00:00Z",
                    "payPurpose": "Оплата услуг",
                },
            ]
        )


class _FakeJumpClient:
    def __init__(self, base_url, client_key):
        pass

    def fetch_all_payments(self, date_from, date_to):
        return iter(
            [
                {
                    "id": "jump-1",
                    "amount": 5000,
                    "commission_bank": 0,
                    "contractor": {"id": 1, "full_name": "Иванов Иван Иванович"},
                    "payment_purpose": "Оплата услуг",
                    "paid_at": "2026-06-01T10:00:00+03:00",
                },
            ]
        )


def _setup_both_integrations(client, headers, db_session):
    client.get("/integrations", headers=headers)  # lazy-seed каталога
    tbank = db_session.query(Integration).filter(Integration.provider == "tinkoff").first()
    jump = db_session.query(Integration).filter(Integration.provider == "jump").first()
    client.post(f"/integrations/{tbank.id}/connect", headers=headers, json={"token": "TBankSandboxToken"})
    client.post(f"/integrations/{jump.id}/connect", headers=headers, json={"token": "jump-client-key"})
    return tbank, jump


def test_tbank_sync_auto_triggers_jump_matching(client, db_session, monkeypatch):
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)
    monkeypatch.setattr(automation_router, "JumpFinanceClient", _FakeJumpClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    tbank, jump = _setup_both_integrations(client, headers, db_session)

    resp = client.post(
        f"/integrations/{tbank.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1

    tx = db_session.query(Transaction).filter(Transaction.external_ref == "tbank:op-1").first()
    assert tx.jump_payment_id == "jump-1"
    assert tx.counterparty_id is not None

    db_session.refresh(jump)
    assert jump.last_sync_at is not None


def test_tbank_sync_without_jump_connected_does_not_fail(client, db_session, monkeypatch):
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    client.get("/integrations", headers=headers)
    tbank = db_session.query(Integration).filter(Integration.provider == "tinkoff").first()
    client.post(f"/integrations/{tbank.id}/connect", headers=headers, json={"token": "TBankSandboxToken"})

    resp = client.post(
        f"/integrations/{tbank.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1


def test_manual_sync_jump_matches_existing_transaction(client, db_session, monkeypatch):
    monkeypatch.setattr(automation_router, "JumpFinanceClient", _FakeJumpClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    client.get("/integrations", headers=headers)
    jump = db_session.query(Integration).filter(Integration.provider == "jump").first()
    client.post(f"/integrations/{jump.id}/connect", headers=headers, json={"token": "jump-client-key"})

    from app.models import Category, Transaction, TxTypeEnum
    from decimal import Decimal

    category = Category(company_id=admin.company_id, name="Импорт", type=TxTypeEnum.expense)
    db_session.add(category)
    db_session.commit()
    tx = Transaction(
        company_id=admin.company_id,
        date_odds="2026-06-01",
        account_id=account.id,
        category_id=category.id,
        type=TxTypeEnum.expense,
        amount=Decimal("5000"),
        currency="RUB",
        amount_rub=Decimal("5000"),
        external_ref="tbank:op-1",
    )
    db_session.add(tx)
    db_session.commit()

    resp = client.post(
        f"/integrations/{jump.id}/sync-jump",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["matched"] == 1

    db_session.refresh(tx)
    assert tx.jump_payment_id == "jump-1"


def test_sync_jump_rejects_non_jump_provider(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    client.get("/integrations", headers=headers)
    tbank = db_session.query(Integration).filter(Integration.provider == "tinkoff").first()

    resp = client.post(
        f"/integrations/{tbank.id}/sync-jump",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01"},
    )
    assert resp.status_code == 400
