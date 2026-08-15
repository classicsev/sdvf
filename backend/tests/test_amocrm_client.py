from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest

from app.integrations.amocrm import AmoCrmClient, AmoCrmError, map_company, map_contact, map_lead


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


def _client(**overrides):
    kwargs = dict(
        subdomain="mvkusno",
        client_id="cid",
        client_secret="csecret",
        access_token="access-1",
        refresh_token="refresh-1",
        page_delay=0,  # тесты не должны реально ждать между "страницами"
    )
    kwargs.update(overrides)
    return AmoCrmClient(**kwargs)


def test_fetch_all_contacts_paginates(monkeypatch):
    pages = {
        1: _FakeResponse(
            200,
            {"_embedded": {"contacts": [{"id": 1, "name": "A"}]}, "_links": {"next": {"href": "x"}}},
        ),
        2: _FakeResponse(200, {"_embedded": {"contacts": [{"id": 2, "name": "B"}]}, "_links": {}}),
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        return pages[params["page"]]

    monkeypatch.setattr(httpx, "get", fake_get)
    client = _client()

    contacts = list(client.fetch_all_contacts())
    assert [c["id"] for c in contacts] == [1, 2]


def test_fetch_all_leads_sends_closed_at_filter(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return _FakeResponse(200, {"_embedded": {"leads": []}, "_links": {}})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = _client()

    list(client.fetch_all_leads(date_from=date(2026, 1, 1)))

    expected_ts = int(datetime.combine(date(2026, 1, 1), datetime.min.time()).timestamp())
    assert captured["params"]["filter[closed_at][from]"] == expected_ts
    assert captured["params"]["with"] == "contacts"


def test_fetch_all_contacts_stops_on_empty_page_even_if_next_present(monkeypatch):
    # Некоторые REST API отдают _links.next даже на пустой последней странице —
    # без этой защиты пагинация зациклилась бы навсегда.
    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse(200, {"_embedded": {"contacts": []}, "_links": {"next": {"href": "x"}}})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = _client()

    assert list(client.fetch_all_contacts()) == []


def test_fetch_all_contacts_respects_max_pages_cap(monkeypatch):
    import app.integrations.amocrm as amocrm_module

    monkeypatch.setattr(amocrm_module, "MAX_PAGES", 2)
    call_count = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        call_count["n"] += 1
        return _FakeResponse(
            200,
            {"_embedded": {"contacts": [{"id": call_count["n"], "name": "x"}]}, "_links": {"next": {"href": "x"}}},
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = _client()

    contacts = list(client.fetch_all_contacts())
    assert len(contacts) == 2
    assert call_count["n"] == 2


def test_get_refreshes_token_on_401_and_retries(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(headers["Authorization"])
        if headers["Authorization"] == "Bearer access-1":
            return _FakeResponse(401)
        return _FakeResponse(200, {"_embedded": {"contacts": []}, "_links": {}})

    def fake_post(url, json=None, timeout=None):
        assert json["grant_type"] == "refresh_token"
        assert json["refresh_token"] == "refresh-1"
        return _FakeResponse(200, {"access_token": "access-2", "refresh_token": "refresh-2"})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = _client()

    list(client.fetch_all_contacts())

    assert calls == ["Bearer access-1", "Bearer access-2"]
    assert client.access_token == "access-2"
    assert client.refresh_token == "refresh-2"
    assert client.tokens_refreshed is True


def test_refresh_tokens_raises_on_failure(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse(401)

    def fake_post(url, json=None, timeout=None):
        return _FakeResponse(400, text="invalid_grant")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = _client()

    with pytest.raises(AmoCrmError):
        list(client.fetch_all_contacts())


def test_get_raises_on_non_200_non_401(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse(500, text="server error")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = _client()

    with pytest.raises(AmoCrmError):
        list(client.fetch_all_contacts())


def test_map_contact_valid_and_invalid():
    assert map_contact({"id": 1, "name": "ООО Мидии Омск"}) == {
        "id": 1,
        "name": "ООО Мидии Омск",
        "company_id": None,
        "phone": None,
        "email": None,
        "position": None,
    }
    assert map_contact({"id": 1}) is None
    assert map_contact({"name": "x"}) is None


def test_map_contact_extracts_company_and_custom_fields():
    raw = {
        "id": 77,
        "name": "Иванов Иван",
        "_embedded": {"companies": [{"id": 500}]},
        "custom_fields_values": [
            {"field_code": "PHONE", "values": [{"value": "+79990000000"}]},
            {"field_code": "EMAIL", "values": [{"value": "ivanov@example.com"}]},
            {"field_code": "POSITION", "values": [{"value": "Закупщик"}]},
        ],
    }
    mapped = map_contact(raw)
    assert mapped["company_id"] == 500
    assert mapped["phone"] == "+79990000000"
    assert mapped["email"] == "ivanov@example.com"
    assert mapped["position"] == "Закупщик"


def test_map_company_valid_and_invalid():
    raw = {
        "id": 500,
        "name": 'ООО "Тихоокеанская Фактория"',
        "custom_fields_values": [
            {"field_code": "PHONE", "values": [{"value": "+74230000000"}]},
            {"field_code": "ADDRESS", "values": [{"value": "г Владивосток"}]},
        ],
    }
    mapped = map_company(raw)
    assert mapped["id"] == 500
    assert mapped["phone"] == "+74230000000"
    assert mapped["address"] == "г Владивосток"
    assert mapped["email"] is None

    assert map_company({"id": 1}) is None
    assert map_company({"name": "x"}) is None


def test_map_lead_won_deal():
    raw = {
        "id": 23021903,
        "name": "Отгрузка 23.11",
        "price": 60000,
        "status_id": 142,
        "closed_at": 1700996643,
        "_embedded": {"contacts": [{"id": 27521389, "is_main": True}]},
    }
    mapped = map_lead(raw)
    assert mapped["external_ref"] == "amocrm:23021903"
    assert mapped["amount"] == Decimal("60000")
    assert mapped["comment"] == "Отгрузка 23.11"
    assert mapped["contact_id"] == 27521389
    assert mapped["date_odds"] == datetime.fromtimestamp(1700996643).date()


def test_map_lead_ignores_non_won_status():
    raw = {"id": 1, "price": 100, "status_id": 39374356, "closed_at": 1700000000}
    assert map_lead(raw) is None


def test_map_lead_missing_price_or_id_returns_none():
    assert map_lead({"id": 1, "status_id": 142, "closed_at": 1700000000}) is None
    assert map_lead({"price": 100, "status_id": 142, "closed_at": 1700000000}) is None


def test_map_lead_zero_price_returns_none():
    assert map_lead({"id": 1, "price": 0, "status_id": 142, "closed_at": 1700000000}) is None


def test_map_lead_missing_closed_at_returns_none():
    assert map_lead({"id": 1, "price": 100, "status_id": 142}) is None


def test_map_lead_without_contacts_has_no_contact_id():
    raw = {"id": 1, "price": 100, "status_id": 142, "closed_at": 1700000000}
    mapped = map_lead(raw)
    assert mapped["contact_id"] is None
