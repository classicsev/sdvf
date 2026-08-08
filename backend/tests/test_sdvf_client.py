from datetime import date

import httpx
import pytest

from app.integrations.sdvf import SdvfClient, SdvfError


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


def _client():
    return SdvfClient(base_url="https://sdvf.ru", api_key="test-key")


def test_get_or_create_organization_sends_key_header_and_payload(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(200, {"id": 5, "naming": "ООО Ромашка", "inn": "7701234567", "created": True})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = _client().get_or_create_organization(inn="7701234567", naming="ООО Ромашка")

    assert result["id"] == 5
    assert captured["url"] == "https://sdvf.ru/api/integration/organizations/"
    assert captured["headers"]["X-API-Key"] == "test-key"
    assert captured["json"]["inn"] == "7701234567"


def test_get_or_create_counterparty(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return _FakeResponse(200, {"id": 8, "naming": json["naming"], "inn": json["inn"], "created": False})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = _client().get_or_create_counterparty(inn="7801234567", naming="ООО Покупатель")

    assert result == {"id": 8, "naming": "ООО Покупатель", "inn": "7801234567", "created": False}


def test_create_invoice_serializes_decimal_lines(monkeypatch):
    from decimal import Decimal

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": 1395, "pdf_url": "https://sdvf.ru/api/integration/invoices/1395/pdf/"})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = _client().create_invoice(
        organization_id=5,
        counterparty_id=8,
        name="TEST-1",
        doc_date=date(2026, 8, 8),
        lines=[{"name": "Мидии", "unit_of_measurement": "кг", "quantity": Decimal("10"), "price": Decimal("350.5"), "amount": Decimal("3505")}],
        nds=20,
        nds_type="onTop",
    )

    assert result["id"] == 1395
    line = captured["json"]["lines"][0]
    assert isinstance(line["quantity"], float)
    assert isinstance(line["price"], float)
    assert captured["json"]["date"] == "2026-08-08"


def test_create_utd(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        assert url == "https://sdvf.ru/api/integration/utd/"
        return _FakeResponse(200, {"id": 2198, "pdf_url": "https://sdvf.ru/api/integration/utd/2198/pdf/"})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = _client().create_utd(
        organization_id=5,
        counterparty_id=8,
        name="УПД-1",
        doc_date=date(2026, 8, 8),
        lines=[{"name": "Мидии", "unit_of_measurement": "кг", "quantity": 10, "price": 350, "amount": 3500}],
    )
    assert result["id"] == 2198


def test_raises_sdvf_error_on_non_200(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return _FakeResponse(401, {"error": "Неверный или отсутствующий X-API-Key"})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(SdvfError):
        _client().get_or_create_organization(inn="123", naming="x")


def test_raises_sdvf_error_on_connection_failure(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(SdvfError):
        _client().get_or_create_organization(inn="123", naming="x")
