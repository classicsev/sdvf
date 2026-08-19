"""Юнит-тесты для integrations/alfabank.py — маппинг сырых операций Alfa API
и постраничный/подневный обход fetch_all_operations (без реальных HTTP-вызовов,
statementDate у Alfa — ОДНА дата за раз, не диапазон, в отличие от Т-Банка)."""

from datetime import date
from decimal import Decimal

from app.integrations.alfabank import AlfaBankClient, map_operation


def test_map_operation_income_uses_rur_transfer_payer_name():
    op = {
        "uuid": "op-1",
        "direction": "CREDIT",
        "amount": {"amount": 1500.50, "currencyName": "RUR"},
        "operationDate": "2026-06-01T00:00:00Z",
        "paymentPurpose": "Оплата по счёту №42",
        "rurTransfer": {"payerName": "ООО Ромашка", "payeeName": "ООО Наша Компания"},
    }
    mapped = map_operation(op)
    assert mapped == {
        "external_ref": "alfa:op-1",
        "date_odds": date(2026, 6, 1),
        "type": "income",
        "amount": Decimal("1500.5"),
        "comment": "Оплата по счёту №42",
        "counterparty_name": "ООО Ромашка",
        "is_financing": False,
    }


def test_map_operation_expense_uses_rur_transfer_payee_name():
    op = {
        "uuid": "op-2",
        "direction": "DEBIT",
        "amount": {"amount": 300, "currencyName": "RUR"},
        "documentDate": "2026-06-02",
        "rurTransfer": {"payerName": "ООО Наша Компания", "payeeName": "ИП Соловьёв"},
    }
    mapped = map_operation(op)
    assert mapped["type"] == "expense"
    assert mapped["counterparty_name"] == "ИП Соловьёв"
    assert mapped["date_odds"] == date(2026, 6, 2)


def test_map_operation_falls_back_to_swift_transfer_for_currency_account():
    op = {
        "uuid": "op-3",
        "direction": "CREDIT",
        "amount": {"amount": 100, "currencyName": "USD"},
        "operationDate": "2026-06-01T00:00:00Z",
        "swiftTransfer": {"orderingCustomerName": "Acme Corp", "beneficiaryCustomerName": "Наша Компания"},
    }
    mapped = map_operation(op)
    assert mapped["counterparty_name"] == "Acme Corp"


def test_map_operation_returns_none_without_uuid():
    op = {"direction": "CREDIT", "amount": {"amount": 100}, "operationDate": "2026-06-01T00:00:00Z"}
    assert map_operation(op) is None


def test_map_operation_returns_none_for_unknown_direction():
    op = {"uuid": "op-4", "direction": "HOLD", "amount": {"amount": 100}, "operationDate": "2026-06-01T00:00:00Z"}
    assert map_operation(op) is None


def test_map_operation_returns_none_for_zero_amount():
    op = {"uuid": "op-5", "direction": "CREDIT", "amount": {"amount": 0}, "operationDate": "2026-06-01T00:00:00Z"}
    assert map_operation(op) is None


def test_map_operation_returns_none_without_date():
    op = {"uuid": "op-6", "direction": "CREDIT", "amount": {"amount": 100}}
    assert map_operation(op) is None


def test_fetch_all_operations_requests_one_call_per_day_and_paginates_within_day(monkeypatch):
    client = AlfaBankClient(
        base_url="https://sandbox.alfabank.ru/api",
        api_key="key",
        cert_pem="cert",
        key_pem="key",
        key_password="pw",
    )
    calls = []

    def fake_fetch_statement_page(account_number, statement_date, page=1):
        calls.append((statement_date, page))
        # 2026-06-01: две страницы (страница 1 непустая, страница 2 пустая — стоп)
        if statement_date == date(2026, 6, 1):
            if page == 1:
                return {"transactions": [{"uuid": "a"}]}
            return {"transactions": []}
        # 2026-06-02: сразу пусто
        return {"transactions": []}

    monkeypatch.setattr(client, "fetch_statement_page", fake_fetch_statement_page)

    ops = list(client.fetch_all_operations("40702810102300000001", date(2026, 6, 1), date(2026, 6, 2)))
    assert [op["uuid"] for op in ops] == ["a"]
    assert calls == [
        (date(2026, 6, 1), 1),
        (date(2026, 6, 1), 2),
        (date(2026, 6, 2), 1),
    ]


def test_fetch_all_operations_defaults_date_to_to_today(monkeypatch):
    client = AlfaBankClient(
        base_url="https://sandbox.alfabank.ru/api", api_key="key", cert_pem="c", key_pem="k", key_password="pw"
    )
    calls = []
    today = date.today()

    def fake_fetch_statement_page(account_number, statement_date, page=1):
        calls.append(statement_date)
        return {"transactions": []}

    monkeypatch.setattr(client, "fetch_statement_page", fake_fetch_statement_page)
    list(client.fetch_all_operations("40702810102300000001", today))
    assert calls == [today]
