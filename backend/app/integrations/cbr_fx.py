from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from xml.etree import ElementTree

import httpx

TIMEOUT = 10.0
CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
# ЦБ публикует курсы только по рабочим дням — на выходной/праздник в ответе
# просто не будет нужной валюты (или будет курс за прошлый рабочий день,
# в зависимости от даты запроса). Ищем назад, но не бесконечно — 10 дней
# с запасом покрывает любые новогодние/майские каникулы.
MAX_LOOKBACK_DAYS = 10


class CbrFxError(Exception):
    pass


def _fetch_rate_for_exact_date(currency: str, on_date: date) -> Optional[Decimal]:
    try:
        resp = httpx.get(CBR_DAILY_URL, params={"date_req": on_date.strftime("%d/%m/%Y")}, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise CbrFxError(f"Ошибка соединения с ЦБ РФ: {exc}") from exc
    if resp.status_code != 200:
        raise CbrFxError(f"ЦБ РФ вернул {resp.status_code}")

    root = ElementTree.fromstring(resp.content)
    for valute in root.findall("Valute"):
        if valute.findtext("CharCode") == currency:
            nominal = Decimal((valute.findtext("Nominal") or "1").replace(",", "."))
            value = Decimal((valute.findtext("Value") or "0").replace(",", "."))
            if nominal == 0:
                return None
            return value / nominal
    return None


def fetch_cbr_rate(currency: str, on_date: date) -> Optional[Decimal]:
    """Официальный курс ЦБ РФ currency→RUB на дату on_date (или на ближайший
    предшествующий рабочий день, если on_date выходной/праздник). None —
    валюта не публикуется ЦБ РФ вообще (не с чем сравнить)."""
    cursor = on_date
    for _ in range(MAX_LOOKBACK_DAYS):
        rate = _fetch_rate_for_exact_date(currency, cursor)
        if rate is not None:
            return rate
        cursor -= timedelta(days=1)
    return None
