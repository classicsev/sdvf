from datetime import date, datetime, time, timezone
from typing import Iterator, Optional

import httpx


class JumpFinanceError(Exception):
    pass


def _to_rfc3339(d: date, end_of_day: bool = False) -> str:
    t = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    return datetime.combine(d, t, tzinfo=timezone.utc).isoformat()


class JumpFinanceClient:
    """Клиент для Jump.Finance OpenAPI — сервис выплат исполнителям
    (самозанятые/ИП), функционально финансируется со счёта в Т-Банке (см.
    пример из документации: банковский счёт компании называется "Т-Банк
    Jump.Finance"). Не создаёт операции в Учёте сам — используется только для
    СОПОСТАВЛЕНИЯ уже загруженных банковских операций с конкретными выплатами
    (см. app/jump_matching.py), поэтому здесь только чтение выплат.

    Авторизация — один статичный ключ, без mTLS: заголовок Client-Key
    (см. https://apidoc.jump.finance/openapi-v1).
    """

    def __init__(self, base_url: str, client_key: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.client_key = client_key
        self.timeout = timeout

    def fetch_payments_page(self, date_from: date, date_to: date, page: int = 1, per_page: int = 100) -> dict:
        headers = {"Accept": "application/json", "Content-Type": "application/json", "Client-Key": self.client_key}
        params = {
            "created_at_from": _to_rfc3339(date_from),
            "created_at_to": _to_rfc3339(date_to, end_of_day=True),
            "page": page,
            "per_page": per_page,
        }
        try:
            resp = httpx.get(
                f"{self.base_url}/payments",
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise JumpFinanceError(f"Ошибка соединения с Jump.Finance API: {exc}") from exc

        if resp.status_code != 200:
            raise JumpFinanceError(f"Jump.Finance API вернул {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def fetch_all_payments(self, date_from: date, date_to: date) -> Iterator[dict]:
        page = 1
        while True:
            data = self.fetch_payments_page(date_from, date_to, page=page)
            items = data.get("items") or []
            for item in items:
                yield item
            meta = data.get("meta") or {}
            last_page = meta.get("last_page")
            if not items or (last_page is not None and page >= last_page):
                break
            page += 1
