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

    def fetch_all_contacts(self) -> Iterator[dict]:
        page = 1
        while page <= MAX_PAGES:
            data = self._get("/api/v4/contacts", params={"page": page, "limit": 250})
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


def map_contact(raw: dict) -> Optional[dict]:
    contact_id = raw.get("id")
    name = raw.get("name")
    if not contact_id or not name:
        return None
    return {"id": contact_id, "name": name}


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
