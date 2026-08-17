from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.integrations.tbank import TBankClient, TBankError, map_operation


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


def test_map_operation_income_from_credit():
    op = {
        "operationId": "op-1",
        "typeOfOperation": "Credit",
        "accountAmount": 1500.50,
        "operationDate": "2026-06-05T10:00:00Z",
        "payPurpose": "Оплата по договору",
        "payer": {"name": "ИП Мальшин"},
    }
    mapped = map_operation(op)
    assert mapped["external_ref"] == "tbank:op-1"
    assert mapped["type"] == "income"
    assert mapped["amount"] == Decimal("1500.5")
    assert mapped["date_odds"] == date(2026, 6, 5)
    assert mapped["comment"] == "Оплата по договору"
    assert mapped["counterparty_name"] == "ИП Мальшин"
    assert mapped["is_financing"] is False


def test_map_operation_flags_credit_line_drawdown_as_financing():
    # incomeLoan — пополнение кредитной линии/овердрафта, не доход бизнеса
    # (см. FINANCING_CATEGORIES) — реальный случай, найден при разборе живых
    # данных: сумма incomeLoan за период совпадала с creditPaymentOuter и ровно
    # на эту величину расходилась с "Приход/Расход" веб-кабинета Т-Банка.
    op = {
        "operationId": "op-loan-1",
        "typeOfOperation": "Credit",
        "accountAmount": 50000.0,
        "operationDate": "2026-06-05T10:00:00Z",
        "category": "incomeLoan",
    }
    mapped = map_operation(op)
    assert mapped["type"] == "income"
    assert mapped["is_financing"] is True


def test_map_operation_flags_credit_line_repayment_as_financing():
    op = {
        "operationId": "op-loan-2",
        "typeOfOperation": "Debit",
        "accountAmount": 50000.0,
        "operationDate": "2026-06-06T10:00:00Z",
        "category": "creditPaymentOuter",
    }
    mapped = map_operation(op)
    assert mapped["type"] == "expense"
    assert mapped["is_financing"] is True


def test_map_operation_regular_category_is_not_financing():
    op = {
        "operationId": "op-regular",
        "typeOfOperation": "Debit",
        "accountAmount": 1000.0,
        "operationDate": "2026-06-06T10:00:00Z",
        "category": "contragentOutcome",
    }
    mapped = map_operation(op)
    assert mapped["is_financing"] is False


def test_map_operation_expense_from_debit_uses_receiver_name():
    op = {
        "operationId": "op-2",
        "typeOfOperation": "Debit",
        "accountAmount": 300.00,
        "docDate": "2026-06-06T00:00:00Z",
        "description": "Комиссия банка",
        "receiver": {"name": "Т-Банк"},
    }
    mapped = map_operation(op)
    assert mapped["type"] == "expense"
    assert mapped["amount"] == Decimal("300.0")
    assert mapped["comment"] == "Комиссия банка"
    assert mapped["counterparty_name"] == "Т-Банк"


def test_map_operation_card_purchase_uses_merchant_name_not_bank():
    # Для карточных операций receiver почти всегда "АО «ТБанк»" (эквайер), а не
    # реальный продавец — реальный продавец лежит в merch.name.
    op = {
        "operationId": "op-5",
        "typeOfOperation": "Debit",
        "accountAmount": 150.0,
        "operationDate": "2026-07-07T02:25:26Z",
        "description": "Оплата в CP PARKOVKI Vladivostok RUS",
        "receiver": {"name": "АО \"ТБанк\""},
        "counterParty": {"name": "АО \"ТБанк\""},
        "merch": {"name": "CP PARKOVKI", "city": "Vladivostok", "country": "RUS"},
    }
    mapped = map_operation(op)
    assert mapped["type"] == "expense"
    assert mapped["counterparty_name"] == "CP PARKOVKI"


def test_map_operation_unknown_type_of_operation_returns_none():
    assert map_operation({"operationId": "op-x", "typeOfOperation": "Hold", "accountAmount": 100}) is None


def test_map_operation_missing_operation_id_returns_none():
    assert map_operation({"typeOfOperation": "Credit", "accountAmount": 100, "operationDate": "2026-06-01"}) is None


def test_map_operation_missing_date_returns_none():
    assert map_operation({"operationId": "op-3", "typeOfOperation": "Credit", "accountAmount": 100}) is None


def test_map_operation_zero_amount_returns_none():
    op = {"operationId": "op-4", "typeOfOperation": "Credit", "accountAmount": 0, "operationDate": "2026-06-01"}
    assert map_operation(op) is None


def test_client_raises_on_non_200(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse(401, {"errorMessage": "Токен недействителен"})

    monkeypatch.setattr(httpx, "get", fake_get)

    client = TBankClient(base_url="https://example.test/openapi", token="bad-token")
    with pytest.raises(TBankError, match="401"):
        client.fetch_statement("40702810900000012345", date(2026, 6, 1))


def test_client_raises_on_connection_error(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "get", fake_get)

    client = TBankClient(base_url="https://example.test/openapi", token="token")
    with pytest.raises(TBankError):
        client.fetch_statement("40702810900000012345", date(2026, 6, 1))


def test_client_paginates_with_cursor(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params.get("cursor"))
        if params.get("cursor") is None:
            return _FakeResponse(200, {"operations": [{"operationId": "1"}], "nextCursor": "page-2"})
        return _FakeResponse(200, {"operations": [{"operationId": "2"}], "nextCursor": None})

    monkeypatch.setattr(httpx, "get", fake_get)

    client = TBankClient(base_url="https://example.test/openapi", token="token")
    ops = list(client.fetch_all_operations("40702810900000012345", date(2026, 6, 1)))

    assert [op["operationId"] for op in ops] == ["1", "2"]
    assert calls == [None, "page-2"]


def test_client_sends_bearer_header(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers
        captured["url"] = url
        return _FakeResponse(200, {"operations": []})

    monkeypatch.setattr(httpx, "get", fake_get)

    client = TBankClient(base_url="https://example.test/openapi", token="my-token")
    client.fetch_statement("40702810900000012345", date(2026, 6, 1))

    assert captured["headers"]["Authorization"] == "Bearer my-token"
    assert captured["url"] == "https://example.test/openapi/api/v1/statement"


def test_client_sends_full_rfc3339_datetime_not_bare_date(monkeypatch):
    # Реальный (не sandbox) Т-Банк API отклоняет голую дату "2026-06-01" ошибкой
    # VALIDATION_ERROR "not a valid date-time" — from/to должны быть полным RFC3339.
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return _FakeResponse(200, {"operations": []})

    monkeypatch.setattr(httpx, "get", fake_get)

    client = TBankClient(base_url="https://example.test/openapi", token="my-token")
    client.fetch_statement("40702810900000012345", date(2026, 6, 1), date(2026, 6, 30))

    assert captured["params"]["from"] == "2026-06-01T00:00:00Z"
    assert captured["params"]["to"] == "2026-06-30T23:59:59Z"
