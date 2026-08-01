from datetime import date
from decimal import Decimal

from app.models import Integration, RoleEnum, Transaction
from app.routers import automation as automation_router
from tests.conftest import auth_headers, make_account, make_user


class _FakeTBankClient:
    """Подменяет TBankClient в роутере, чтобы не ходить в реальный банк."""

    calls = []

    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token

    def fetch_all_operations(self, account_number, date_from, date_to=None):
        _FakeTBankClient.calls.append((account_number, date_from, date_to))
        return iter(
            [
                {
                    "operationId": "op-1",
                    "credit": "31500.00",
                    "operationDate": "2026-06-01T00:00:00",
                    "payPurpose": "ТД-620 от 26.05",
                    "payer": {"name": "ИП Мальшин"},
                },
                {
                    "operationId": "op-2",
                    "debit": "4990.00",
                    "operationDate": "2026-06-02T00:00:00",
                    "description": "Комиссия банка",
                },
                # Операция без operationId — map_operation вернёт None, должна быть пропущена
                {"credit": "100", "operationDate": "2026-06-03T00:00:00"},
            ]
        )


def _setup_connected_tbank(client, headers, db_session):
    client.get("/integrations", headers=headers)  # lazy-seed каталога
    integration = db_session.query(Integration).filter(Integration.provider == "tinkoff").first()
    client.post(f"/integrations/{integration.id}/connect", headers=headers, json={"token": "TBankSandboxToken"})
    return integration


def test_sync_creates_transactions_and_dedupes_on_rerun(client, db_session, monkeypatch):
    _FakeTBankClient.calls = []
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    integration = _setup_connected_tbank(client, headers, db_session)

    resp = client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2  # третья операция без operationId пропущена
    assert body["skipped"] == 1

    created = db_session.query(Transaction).filter(Transaction.external_ref.isnot(None)).all()
    assert len(created) == 2
    by_ref = {t.external_ref: t for t in created}
    income_tx = by_ref["tbank:op-1"]
    assert income_tx.type.value == "income"
    assert income_tx.amount == Decimal("31500.00")
    assert income_tx.comment == "ТД-620 от 26.05"
    expense_tx = by_ref["tbank:op-2"]
    assert expense_tx.type.value == "expense"
    assert expense_tx.amount == Decimal("4990.00")

    db_session.refresh(integration)
    assert integration.last_sync_at is not None

    # повторный синк — обе операции уже есть, новых транзакций быть не должно
    resp = client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 0
    assert resp.json()["skipped"] == 3

    total = db_session.query(Transaction).filter(Transaction.external_ref.isnot(None)).count()
    assert total == 2  # дублей не появилось


def test_sync_auto_creates_counterparty_from_payer_name(client, db_session, monkeypatch):
    _FakeTBankClient.calls = []
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    integration = _setup_connected_tbank(client, headers, db_session)

    client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01"},
    )

    from app.models import Counterparty

    cp = db_session.query(Counterparty).filter(Counterparty.name == "ИП Мальшин").first()
    assert cp is not None


def test_sync_fails_when_tbank_returns_error(client, db_session, monkeypatch):
    class _FailingClient:
        def __init__(self, base_url, token):
            pass

        def fetch_all_operations(self, account_number, date_from, date_to=None):
            from app.integrations.tbank import TBankError

            raise TBankError("Т-Банк API вернул 401: Токен недействителен")

    monkeypatch.setattr(automation_router, "TBankClient", _FailingClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    integration = _setup_connected_tbank(client, headers, db_session)

    resp = client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01"},
    )
    assert resp.status_code == 502
    assert "401" in resp.json()["detail"]

    # ничего не должно было закоммититься
    assert db_session.query(Transaction).filter(Transaction.external_ref.isnot(None)).count() == 0
    db_session.refresh(integration)
    assert integration.last_sync_at is None
