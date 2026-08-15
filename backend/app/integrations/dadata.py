from typing import Optional

import httpx

TIMEOUT = 10.0
FIND_PARTY_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"


class DadataError(Exception):
    pass


class DadataClient:
    """Клиент подсказок DaData — поиск организации/ИП по ИНН в ЕГРЮЛ/ЕГРИП.
    Тот же метод, что использует СДВФ (user/views.py::find_company_by_inn), чтобы
    реквизиты в обоих сервисах заполнялись из одного источника и совпадали."""

    def __init__(self, api_key: str, timeout: float = TIMEOUT):
        self.api_key = api_key
        self.timeout = timeout

    def _find_party(self, payload: dict) -> list[dict]:
        try:
            resp = httpx.post(
                FIND_PARTY_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token {self.api_key}",
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise DadataError(f"Ошибка соединения с DaData: {exc}") from exc

        if resp.status_code != 200:
            raise DadataError(f"DaData вернул {resp.status_code}")
        return resp.json().get("suggestions") or []

    def find_by_inn(self, inn: str) -> Optional[dict]:
        """None — если по ИНН ничего не нашлось. Для 10/12-значных ИНН DaData
        иногда требует явного указания типа (LEGAL/INDIVIDUAL) — повторяем
        запрос с уточнением, как это сделано в СДВФ."""
        suggestions = self._find_party({"query": inn})
        if not suggestions:
            party_type = "INDIVIDUAL" if len(inn) == 12 else "LEGAL" if len(inn) == 10 else None
            if party_type:
                suggestions = self._find_party({"query": inn, "type": party_type})
        if not suggestions:
            return None

        row = suggestions[0]
        data = row.get("data") or {}
        management = data.get("management") or {}
        opf_short = (data.get("opf") or {}).get("short") or ""
        is_individual = data.get("type") == "INDIVIDUAL" or opf_short == "ИП"

        return {
            "name": row.get("value") or "",
            "inn": data.get("inn") or inn,
            # У ИП КПП не существует в принципе — отдаём пустую строку, а не null,
            # чтобы фронт мог просто подставить значение в поле формы.
            "kpp": "" if is_individual else (data.get("kpp") or ""),
            "ogrn": data.get("ogrn") or "",
            "address": (data.get("address") or {}).get("value") or "",
            "party_type": "individual" if is_individual else "legal_entity",
            "supervisor": "" if is_individual else (management.get("name") or ""),
            "supervisor_position": "" if is_individual else (management.get("post") or ""),
        }
