from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.integrations.cbr_fx import CbrFxError, fetch_cbr_rate

CNY_XML = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="07.09.2026" name="Foreign Currency Market">
<Valute ID="R01375">
<NumCode>156</NumCode>
<CharCode>CNY</CharCode>
<Nominal>1</Nominal>
<Name>Китайский юань</Name>
<Value>12,5000</Value>
</Valute>
</ValCurs>""".encode("windows-1251")

# KRW котируется за 100 единиц — проверяет деление на Nominal
KRW_XML = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="07.09.2026" name="Foreign Currency Market">
<Valute ID="R01815">
<NumCode>410</NumCode>
<CharCode>KRW</CharCode>
<Nominal>100</Nominal>
<Name>Вон</Name>
<Value>6,4500</Value>
</Valute>
</ValCurs>""".encode("windows-1251")

EMPTY_XML = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="06.09.2026" name="Foreign Currency Market">
</ValCurs>""".encode("windows-1251")


def _resp(status_code, content):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    return resp


def test_fetch_cbr_rate_parses_nominal_one():
    with patch("httpx.get", return_value=_resp(200, CNY_XML)) as mocked:
        rate = fetch_cbr_rate("CNY", date(2026, 9, 7))
    assert rate == Decimal("12.5")
    mocked.assert_called_once()


def test_fetch_cbr_rate_divides_by_nominal():
    with patch("httpx.get", return_value=_resp(200, KRW_XML)):
        rate = fetch_cbr_rate("KRW", date(2026, 9, 7))
    assert rate == Decimal("0.0645")  # 6.45 / 100


def test_fetch_cbr_rate_falls_back_to_previous_business_day():
    """Дата запроса — выходной, ЦБ не публикует курс (пустой ValCurs) —
    ищем на день раньше и находим."""
    with patch("httpx.get", side_effect=[_resp(200, EMPTY_XML), _resp(200, CNY_XML)]) as mocked:
        rate = fetch_cbr_rate("CNY", date(2026, 9, 7))
    assert rate == Decimal("12.5")
    assert mocked.call_count == 2


def test_fetch_cbr_rate_unknown_currency_returns_none_after_lookback():
    with patch("httpx.get", return_value=_resp(200, EMPTY_XML)) as mocked:
        rate = fetch_cbr_rate("XYZ", date(2026, 9, 7))
    assert rate is None
    assert mocked.call_count == 10  # MAX_LOOKBACK_DAYS


def test_fetch_cbr_rate_network_error_raises_cbr_fx_error():
    with patch("httpx.get", side_effect=httpx.ConnectError("boom")):
        with pytest.raises(CbrFxError):
            fetch_cbr_rate("CNY", date(2026, 9, 7))


def test_fetch_cbr_rate_non_200_raises_cbr_fx_error():
    with patch("httpx.get", return_value=_resp(500, b"")):
        with pytest.raises(CbrFxError):
            fetch_cbr_rate("CNY", date(2026, 9, 7))
