"""Юнит-тесты для integrations/jumpfinance.py — пагинация через meta.last_page."""

from datetime import date

from app.integrations.jumpfinance import JumpFinanceClient


def test_fetch_all_payments_paginates_until_last_page(monkeypatch):
    client = JumpFinanceClient(base_url="https://api.jump.finance/services/openapi", client_key="key")
    calls = []

    def fake_fetch_payments_page(date_from, date_to, page=1, per_page=100):
        calls.append(page)
        if page == 1:
            return {"items": [{"id": "1"}, {"id": "2"}], "meta": {"last_page": 2}}
        return {"items": [{"id": "3"}], "meta": {"last_page": 2}}

    monkeypatch.setattr(client, "fetch_payments_page", fake_fetch_payments_page)
    items = list(client.fetch_all_payments(date(2026, 6, 1), date(2026, 6, 30)))
    assert [i["id"] for i in items] == ["1", "2", "3"]
    assert calls == [1, 2]


def test_fetch_all_payments_stops_on_empty_page(monkeypatch):
    client = JumpFinanceClient(base_url="https://api.jump.finance/services/openapi", client_key="key")

    def fake_fetch_payments_page(date_from, date_to, page=1, per_page=100):
        if page == 1:
            return {"items": [{"id": "1"}], "meta": {}}
        return {"items": [], "meta": {}}

    monkeypatch.setattr(client, "fetch_payments_page", fake_fetch_payments_page)
    items = list(client.fetch_all_payments(date(2026, 6, 1), date(2026, 6, 30)))
    assert [i["id"] for i in items] == ["1"]
