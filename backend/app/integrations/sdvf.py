from datetime import date
from decimal import Decimal
from typing import Optional

import httpx

TIMEOUT = 30.0


class SdvfError(Exception):
    pass


class SdvfClient:
    """Клиент для машинного API СДВФ (sdvf.ru, integration_api Django-приложение) —
    генерация Счёт/УПД по данным заказа из Склада. Не сам генерирует PDF —
    только создаёт документ и отдаёт ссылку, рендер целиком на стороне СДВФ
    (weasyprint + их шаблоны, см. invoice/services.py в их репозитории)."""

    def __init__(self, base_url: str, api_key: str, timeout: float = TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = httpx.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={"X-API-Key": self.api_key},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise SdvfError(f"Ошибка соединения с СДВФ: {exc}") from exc

        return self._parse(resp)

    def _get(self, path: str, params: dict) -> dict:
        try:
            resp = httpx.get(
                f"{self.base_url}{path}",
                params=params,
                headers={"X-API-Key": self.api_key},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise SdvfError(f"Ошибка соединения с СДВФ: {exc}") from exc

        return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> dict:
        if resp.status_code != 200:
            detail = resp.text[:300]
            try:
                detail = resp.json().get("error", detail)
            except ValueError:
                pass
            raise SdvfError(f"СДВФ вернул {resp.status_code}: {detail}")
        return resp.json()

    def list_counterparties(self, organization_inn: str, inn: Optional[str] = None) -> list[dict]:
        """Контрагенты аккаунта, которому принадлежит организация с этим ИНН.
        organization_inn обязателен: без него СДВФ отдаст карточки служебного
        пользователя интеграции, а не реального клиента (см. integration_api)."""
        params = {"organization_inn": organization_inn}
        if inn:
            params["inn"] = inn
        return self._get("/api/integration/counterparties/list/", params).get("items") or []

    def get_or_create_organization(
        self,
        inn: str,
        naming: str,
        *,
        kpp: Optional[str] = None,
        ogrn: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> dict:
        return self._post(
            "/api/integration/organizations/",
            {"inn": inn, "naming": naming, "kpp": kpp, "ogrn": ogrn, "address": address, "phone": phone},
        )

    def get_or_create_counterparty(
        self,
        inn: str,
        naming: str,
        *,
        kpp: Optional[str] = None,
        ogrn: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        organization_inn: Optional[str] = None,
    ) -> dict:
        # organization_inn определяет, в чьём аккаунте СДВФ появится карточка —
        # без него она уйдёт служебному пользователю и клиент её не увидит.
        return self._post(
            "/api/integration/counterparties/",
            {
                "inn": inn,
                "naming": naming,
                "kpp": kpp,
                "ogrn": ogrn,
                "address": address,
                "phone": phone,
                "organization_inn": organization_inn,
            },
        )

    def create_invoice(
        self,
        *,
        organization_id: int,
        counterparty_id: int,
        name: str,
        doc_date: date,
        lines: list[dict],
        nds: int = 0,
        nds_type: str = "onTop",
        currency: str = "RUB",
    ) -> dict:
        return self._post(
            "/api/integration/invoices/",
            {
                "organization_id": organization_id,
                "counterparty_id": counterparty_id,
                "name": name,
                "date": doc_date.isoformat(),
                "nds": nds,
                "nds_type": nds_type,
                "currency": currency,
                "lines": [_serialize_line(line) for line in lines],
            },
        )

    def create_utd(
        self,
        *,
        organization_id: int,
        counterparty_id: int,
        name: str,
        doc_date: date,
        lines: list[dict],
        nds: int = -1,
        nds_type: str = "onTop",
        currency: str = "RUB",
        shipment_date: Optional[date] = None,
    ) -> dict:
        return self._post(
            "/api/integration/utd/",
            {
                "organization_id": organization_id,
                "counterparty_id": counterparty_id,
                "name": name,
                "date": doc_date.isoformat(),
                "nds": nds,
                "nds_type": nds_type,
                "currency": currency,
                "shipment_date": shipment_date.isoformat() if shipment_date else None,
                "lines": [_serialize_line(line) for line in lines],
            },
        )


def _serialize_line(line: dict) -> dict:
    """quantity/price/amount могут прийти как Decimal (из ORM) — JSON их не
    умеет сериализовать напрямую, приводим к float/str перед отправкой."""
    serialized = dict(line)
    for key in ("quantity", "price", "amount", "discount"):
        value = serialized.get(key)
        if isinstance(value, Decimal):
            serialized[key] = float(value)
    return serialized
