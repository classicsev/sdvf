import io
import re
from datetime import date
from decimal import Decimal

import pdfplumber

from app.statement_parsers.base import DedupKeyBuilder, ParsedStatement, StatementParseError

# Альфа-Банк «Выписка по счету» (физлицо) — одна строка на операцию: дата проводки,
# код операции (используем как есть — реально уникален в рамках банка, в отличие от
# Т-Банка/Сбера/ВТБ в этих справках), начало описания, сумма (явный минус на расход,
# без знака = приход). Хвост описания вроде "Без НДС." иногда переносится на
# следующую строку без даты — считаем её продолжением. Единственный банк из четырёх,
# где в самой выписке есть срез остатка сразу на начало И на конец периода.
LINE_A = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(\S+)\s+(.+?)\s+([+-]?[\d\s\xa0]+,\d{2})\s*RUR$")

STOP_MARKERS = (
    "Уполномоченное лицо",
    "подпись сотрудника",
    "Страница",
    "АО «АЛЬФА-БАНК»",
    "alfabank.ru",
    "Москва, 107078",
    "+7 495",
    "к/с 3010",
)

ACCOUNT_RE = re.compile(r"Номер счета\s+(\d+)")
PERIOD_RE = re.compile(r"За период с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})")
OPENING_RE = re.compile(r"Входящий остаток\s+([\d\s\xa0]+,\d{2})\s*RUR")
CLOSING_RE = re.compile(r"Исходящий остаток\s+([\d\s\xa0]+,\d{2})\s*RUR")


def _is_stop(line: str) -> bool:
    return any(marker in line for marker in STOP_MARKERS)


def _parse_ru_date(s: str) -> date:
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


def _clean_amount(s: str) -> Decimal:
    return abs(Decimal(s.replace(" ", "").replace("\xa0", "").replace(",", ".").lstrip("+")))


def sniff(text: str) -> bool:
    if "АО «АЛЬФА-БАНК»" in text or "alfabank.ru" in text:
        return True
    return "Дата проводки" in text and "Код операции" in text and "Входящий остаток" in text


def parse(pdf_bytes: bytes) -> ParsedStatement:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return parse_text(text)


def parse_text(text: str) -> ParsedStatement:
    m_account = ACCOUNT_RE.search(text)
    account_number = m_account.group(1) if m_account else None

    period_from = period_to = None
    m_period = PERIOD_RE.search(text)
    if m_period:
        period_from = _parse_ru_date(m_period.group(1))
        period_to = _parse_ru_date(m_period.group(2))

    opening_balance = None
    m_opening = OPENING_RE.search(text)
    if m_opening:
        opening_balance = _clean_amount(m_opening.group(1))

    closing_balance = None
    m_closing = CLOSING_RE.search(text)
    if m_closing:
        closing_balance = _clean_amount(m_closing.group(1))

    dedup = DedupKeyBuilder("alfabank_pdf", account_number)
    transactions = []
    lines = [l for l in text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        ma = LINE_A.match(line)
        if not ma:
            i += 1
            continue
        date_s, code, desc1, amount_s = ma.groups()
        date_odds = _parse_ru_date(date_s)
        is_income = not amount_s.strip().startswith("-")
        amount = _clean_amount(amount_s)
        i += 1

        desc_parts = [desc1]
        while i < len(lines) and not LINE_A.match(lines[i].strip()) and not _is_stop(lines[i]):
            desc_parts.append(lines[i].strip())
            i += 1

        description = " ".join(desc_parts).strip()
        tx_type = "income" if is_income else "expense"
        transactions.append(
            {
                "external_ref": dedup.build(date_odds, amount, description, extra=code),
                "date_odds": date_odds,
                "type": tx_type,
                "amount": amount,
                "comment": description or None,
                "counterparty_name": None,
                "is_financing": False,
            }
        )

    if not transactions:
        raise StatementParseError("В выписке Альфа-Банка не найдено ни одной операции")

    return ParsedStatement(
        bank="alfabank",
        account_number=account_number,
        period_from=period_from,
        period_to=period_to,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        closing_balance_date=period_to,
        transactions=transactions,
    )
