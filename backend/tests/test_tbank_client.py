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
        "credit": "1500.50",
        "debit": None,
        "operationDate": "2026-06-05T10:00:00",
        "payPurpose": "Оплата по договору",
        "payer": {"name": "ИП Мальшин"},
    }
    mapped = map_operation(op)
    assert mapped["external_ref"] == "tbank:op-1"
    assert mapped["type"] == "income"
    assert mapped["amount"] == Decimal("1500.50")
    assert mapped["date_odds"] == date(2026, 6, 5)
    assert mapped["comment"] == "Оплата по договору"
    assert mapped["counterparty_name"] == "ИП Мальшин"


def test_map_operation_expense_from_debit_uses_receiver_name():
    op = {
        "operationId": "op-2",
        "credit": None,
        "debit": "300.00",
        "docDate": "2026-06-06T00:00:00",
        "description": "Комиссия банка",
        "receiver": {"name": "Т-Банк"},
    }
    mapped = map_operation(op)
    assert mapped["type"] == "expense"
    assert mapped["amount"] == Decimal("300.00")
    assert mapped["comment"] == "Комиссия банка"
    assert mapped["counterparty_name"] == "Т-Банк"


def test_map_operation_missing_operation_id_returns_none():
    assert map_operation({"credit": "100", "operationDate": "2026-06-01"}) is None


def test_map_operation_missing_date_returns_none():
    assert map_operation({"operationId": "op-3", "credit": "100"}) is None


def test_map_operation_zero_amounts_returns_none():
    assert map_operation({"operationId": "op-4", "credit": "0", "debit": None, "operationDate": "2026-06-01"}) is None


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
