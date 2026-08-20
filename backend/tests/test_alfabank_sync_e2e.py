"""E2E синк Альфа-Банка через /integrations/{id}/sync — по образцу
test_tbank_sync_e2e.py, но с отдельным подключением (/connect-alfabank,
сертификат+ключ+API-ключ вместо одного статичного токена)."""

from decimal import Decimal

from app.models import Integration, RoleEnum, Transaction
from app.routers import automation as automation_router
from tests.conftest import auth_headers, make_account, make_user

ALFA_CONNECT_PAYLOAD = {
    "api_key": "test-api-key",
    "cert_pem": "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
    "key_pem": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
    "key_password": "alfabank",
}


class _FakeAlfaBankClient:
    """Подменяет AlfaBankClient в роутере, чтобы не ходить в реальный банк."""

    def __init__(self, base_url, api_key, cert_pem, key_pem, key_password):
        self.base_url = base_url
        self.api_key = api_key
        self.cert_pem = cert_pem
        self.key_pem = key_pem
        self.key_password = key_password

    def fetch_all_operations(self, account_number, date_from, date_to=None):
        return iter(
            [
                {
                    "uuid": "op-1",
                    "direction": "CREDIT",
                    "amount": {"amount": 31500.00, "currencyName": "RUR"},
                    "operationDate": "2026-06-01T00:00:00Z",
                    "paymentPurpose": "ТД-620 от 26.05",
                    "rurTransfer": {"payerName": "ИП Мальшин"},
                },
                {
                    "uuid": "op-2",
                    "direction": "DEBIT",
                    "amount": {"amount": 4990.00, "currencyName": "RUR"},
                    "operationDate": "2026-06-02T00:00:00Z",
                    "rurTransfer": {"payeeName": "Комиссия банка"},
                },
                # Операция без uuid — map_operation вернёт None, должна быть пропущена
                {"direction": "CREDIT", "amount": {"amount": 100}, "operationDate": "2026-06-03T00:00:00Z"},
            ]
        )


def _setup_connected_alfa(client, headers, db_session):
    client.get("/integrations", headers=headers)  # lazy-seed каталога
    integration = db_session.query(Integration).filter(Integration.provider == "alfa").first()
    resp = client.post(f"/integrations/{integration.id}/connect-alfabank", headers=headers, json=ALFA_CONNECT_PAYLOAD)
    assert resp.status_code == 200, resp.text
    return integration


def test_connect_alfabank_rejects_generic_connect_endpoint(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    client.get("/integrations", headers=headers)
    integration = db_session.query(Integration).filter(Integration.provider == "alfa").first()

    resp = client.post(f"/integrations/{integration.id}/connect", headers=headers, json={"token": "whatever"})
    assert resp.status_code == 400


def test_sync_creates_transactions_and_dedupes_on_rerun(client, db_session, monkeypatch):
    monkeypatch.setattr(automation_router, "AlfaBankClient", _FakeAlfaBankClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810102300000001")
    integration = _setup_connected_alfa(client, headers, db_session)

    resp = client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert body["skipped_unparseable"] == 1

    created = db_session.query(Transaction).filter(Transaction.external_ref.isnot(None)).all()
    by_ref = {t.external_ref: t for t in created}
    income_tx = by_ref["alfa:op-1"]
    assert income_tx.type.value == "income"
    assert income_tx.amount == Decimal("31500.00")
    assert income_tx.bank_payment_purpose == "ТД-620 от 26.05"
    expense_tx = by_ref["alfa:op-2"]
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
    assert resp.json()["skipped_duplicate"] == 2

    total = db_session.query(Transaction).filter(Transaction.external_ref.isnot(None)).count()
    assert total == 2


def test_sync_requires_date_from_for_alfa(client, db_session, monkeypatch):
    """У Alfa API statementDate обязателен и это ОДНА дата — в отличие от
    Т-Банка, здесь нельзя молча синкать "всю историю" без даты начала."""
    monkeypatch.setattr(automation_router, "AlfaBankClient", _FakeAlfaBankClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810102300000001")
    integration = _setup_connected_alfa(client, headers, db_session)

    # date_from не передан — схема IntegrationSyncIn требует его всегда,
    # поэтому запрос вообще не пройдёт валидацию (422), а не наш 400.
    resp = client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id},
    )
    assert resp.status_code == 422


def test_sync_fails_when_alfa_returns_error(client, db_session, monkeypatch):
    class _FailingClient:
        def __init__(self, base_url, api_key, cert_pem, key_pem, key_password):
            pass

        def fetch_all_operations(self, account_number, date_from, date_to=None):
            from app.integrations.alfabank import AlfaBankError

            raise AlfaBankError("Alfa API вернул 401: invalid_token")

    monkeypatch.setattr(automation_router, "AlfaBankClient", _FailingClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810102300000001")
    integration = _setup_connected_alfa(client, headers, db_session)

    resp = client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01"},
    )
    assert resp.status_code == 502
    assert "401" in resp.json()["detail"]
    assert db_session.query(Transaction).filter(Transaction.external_ref.isnot(None)).count() == 0
    db_session.refresh(integration)
    assert integration.last_sync_at is None


def test_sync_rejects_wide_date_range_for_alfa(client, db_session, monkeypatch):
    """Alfa API отдаёт выписку по одному дню за раз — широкий диапазон
    означает столько же последовательных запросов к банку и рискует
    затянуться на минуты (см. HANDOVER.md, реальный кейс: ~230 дней "зависли")."""
    monkeypatch.setattr(automation_router, "AlfaBankClient", _FakeAlfaBankClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810102300000001")
    integration = _setup_connected_alfa(client, headers, db_session)

    resp = client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-01-01", "date_to": "2026-08-19"},
    )
    assert resp.status_code == 400
    assert "92" in resp.json()["detail"]


def test_sync_dedupes_same_external_ref_seen_twice_in_one_batch(client, db_session, monkeypatch):
    """Регрессия: песочница Alfa отдаёт одну и ту же тестовую операцию
    (тот же uuid) на разные дни — раньше это падало необработанной
    IntegrityError (UniqueViolation) при батч-вставке вместо аккуратного
    skipped_duplicate, потому что дедуп проверялся только против уже
    сохранённых в БД записей, а не внутри текущей пачки."""

    class _RepeatingClient:
        def __init__(self, base_url, api_key, cert_pem, key_pem, key_password):
            pass

        def fetch_all_operations(self, account_number, date_from, date_to=None):
            op = {
                "uuid": "same-op-every-day",
                "direction": "DEBIT",
                "amount": {"amount": 10.0, "currencyName": "RUR"},
                "operationDate": "2025-12-31T00:00:00Z",
                "paymentPurpose": "Штраф ГИБДД",
                "rurTransfer": {"payeeName": "ГИБДД"},
            }
            return iter([dict(op), dict(op), dict(op)])

    monkeypatch.setattr(automation_router, "AlfaBankClient", _RepeatingClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810102300000001")
    integration = _setup_connected_alfa(client, headers, db_session)

    resp = client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01", "date_to": "2026-06-03"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped_duplicate"] == 2
    assert (
        db_session.query(Transaction).filter(Transaction.external_ref == "alfa:same-op-every-day").count() == 1
    )
