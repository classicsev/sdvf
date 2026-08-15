import time
from datetime import date, datetime
from decimal import Decimal
from typing import Iterator, Optional

import httpx

# Зарезервированные amoCRM статусы, одинаковые для любого аккаунта/воронки —
# 142 = "Успешно реализовано", 143 = "Закрыто и не реализовано".
# Проверено вживую на реальном аккаунте (mvkusno.amocrm.ru).
WON_STATUS_ID = 142

# amoCRM документирует лимит ~7 запросов/сек на интеграцию; без паузы между страницами
# полная синхронизация аккаунта с сотнями страниц контактов/сделок рискует словить
# рейт-лимит (проверено вживую — после серии запросов без пауз API переставал отвечать
# даже на простейшие запросы). PAGE_DELAY_SECONDS держит нас заметно ниже лимита.
PAGE_DELAY_SECONDS = 0.3
# Жёсткий потолок страниц — защита от зацикливания, если API когда-либо отдаст
# _links.next на пустой последней странице (у части REST API так бывает).
MAX_PAGES = 500


class AmoCrmError(Exception):
    pass


class AmoCrmClient:
    """Клиент для amoCRM API v4.

    В отличие от Т-Банка, у amoCRM для «внешней интеграции» нет варианта статичного
    долгосрочного токена (проверено вживую на реальном аккаунте — попытка использовать
    сгенерированный «долгосрочный токен» напрямую отдавала 401) — только OAuth2:
    access_token живёт ограниченное время, обновляется через refresh_token. При 401
    клиент сам обновляет пару токенов и повторяет запрос; вызывающий код должен проверить
    tokens_refreshed после использования клиента и сохранить новую пару.
    """

    def __init__(
        self,
        subdomain: str,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
        redirect_uri: str = "https://localhost/",
        timeout: float = 45.0,
        page_delay: float = PAGE_DELAY_SECONDS,
    ):
        self.base_url = f"https://{subdomain}.amocrm.ru"
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.redirect_uri = redirect_uri
        self.timeout = timeout
        self.page_delay = page_delay
        self.tokens_refreshed = False

    def _refresh_tokens(self) -> None:
        try:
            resp = httpx.post(
                f"{self.base_url}/oauth2/access_token",
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "redirect_uri": self.redirect_uri,
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise AmoCrmError(f"Ошибка соединения с amoCRM при обновлении токена: {exc}") from exc

        if resp.status_code != 200:
            raise AmoCrmError(f"Не удалось обновить токен amoCRM ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.tokens_refreshed = True

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        def _do() -> httpx.Response:
            return httpx.get(
                f"{self.base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=self.timeout,
            )

        try:
            resp = _do()
            if resp.status_code == 401:
                self._refresh_tokens()
                resp = _do()
        except httpx.HTTPError as exc:
            raise AmoCrmError(f"Ошибка соединения с amoCRM: {exc}") from exc

        if resp.status_code == 204:
            return None
        if resp.status_code != 200:
            raise AmoCrmError(f"amoCRM API вернул {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def fetch_all_companies(self) -> Iterator[dict]:
        """Компании amoCRM — именно они становятся карточками контрагентов
        (компания первична, контакты подвязываются к ней)."""
        page = 1
        while page <= MAX_PAGES:
            data = self._get("/api/v4/companies", params={"page": page, "limit": 250})
            if not data:
                break
            items = (data.get("_embedded") or {}).get("companies") or []
            for company in items:
                yield company
            if not items or "next" not in (data.get("_links") or {}):
                break
            page += 1
            time.sleep(self.page_delay)

    def fetch_all_contacts(self) -> Iterator[dict]:
        # with=companies — иначе в ответе не будет связи контакта с компанией,
        # и мы не сможем подвязать его к нужной карточке контрагента.
        page = 1
        while page <= MAX_PAGES:
            data = self._get("/api/v4/contacts", params={"page": page, "limit": 250, "with": "companies"})
            if not data:
                break
            items = (data.get("_embedded") or {}).get("contacts") or []
            for contact in items:
                yield contact
            # Останавливаемся и по отсутствию next, и по пустой странице — некоторые
            # REST API отдают _links.next даже на последней (пустой) странице.
            if not items or "next" not in (data.get("_links") or {}):
                break
            page += 1
            time.sleep(self.page_delay)

    def fetch_all_leads(self, date_from: Optional[date] = None) -> Iterator[dict]:
        params = {"limit": 250, "with": "contacts"}
        if date_from:
            params["filter[closed_at][from]"] = int(datetime.combine(date_from, datetime.min.time()).timestamp())

        page = 1
        while page <= MAX_PAGES:
            page_params = {**params, "page": page}
            data = self._get("/api/v4/leads", params=page_params)
            if not data:
                break
            items = (data.get("_embedded") or {}).get("leads") or []
            for lead in items:
                yield lead
            if not items or "next" not in (data.get("_links") or {}):
                break
            page += 1
            time.sleep(self.page_delay)


def _custom_field_value(raw: dict, field_code: str) -> Optional[str]:
    """Значение поля по коду (PHONE/EMAIL/POSITION). У amoCRM это не плоские
    атрибуты, а список custom_fields_values с вложенными values."""
    for field in raw.get("custom_fields_values") or []:
        if field.get("field_code") != field_code:
            continue
        values = field.get("values") or []
        if values and values[0].get("value"):
            return str(values[0]["value"])
    return None


def map_contact(raw: dict) -> Optional[dict]:
    contact_id = raw.get("id")
    name = raw.get("name")
    if not contact_id or not name:
        return None

    # Компания, к которой привязан контакт (fetch_all_contacts запрашивает
    # with=companies). Без неё контакт "висит в воздухе" — тогда карточкой
    # контрагента становится он сам (физлицо).
    companies = (raw.get("_embedded") or {}).get("companies") or []
    return {
        "id": contact_id,
        "name": name,
        "company_id": companies[0]["id"] if companies else None,
        "phone": _custom_field_value(raw, "PHONE"),
        "email": _custom_field_value(raw, "EMAIL"),
        "position": _custom_field_value(raw, "POSITION"),
    }


def map_company(raw: dict) -> Optional[dict]:
    """Компания amoCRM → карточка контрагента. ИНН у amoCRM в стандартных полях
    нет — он приходит только из СДВФ или вводится руками, поэтому None."""
    company_id = raw.get("id")
    name = raw.get("name")
    if not company_id or not name:
        return None
    return {
        "id": company_id,
        "name": name,
        "phone": _custom_field_value(raw, "PHONE"),
        "email": _custom_field_value(raw, "EMAIL"),
        "address": _custom_field_value(raw, "ADDRESS"),
    }


def map_lead(raw: dict) -> Optional[dict]:
    """Только сделки в статусе "Успешно реализовано" — маппинг в доходную транзакцию."""
    if raw.get("status_id") != WON_STATUS_ID:
        return None

    lead_id = raw.get("id")
    price = raw.get("price")
    if not lead_id or not price:
        return None
    amount = Decimal(str(price))
    if amount <= 0:
        return None

    closed_ts = raw.get("closed_at") or raw.get("updated_at")
    if not closed_ts:
        return None
    date_odds = datetime.fromtimestamp(closed_ts).date()

    contacts = (raw.get("_embedded") or {}).get("contacts") or []
    contact_id = contacts[0]["id"] if contacts else None

    return {
        "external_ref": f"amocrm:{lead_id}",
        "date_odds": date_odds,
        "amount": amount,
        "comment": raw.get("name"),
        "contact_id": contact_id,
    }
