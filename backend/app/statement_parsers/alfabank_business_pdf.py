import io
import re
from datetime import date
from decimal import Decimal
from typing import List, Optional

import pdfplumber

from app.statement_parsers.base import DedupKeyBuilder, ParsedStatement, StatementParseError

# Альфа-Банк «Выписка по счёту» для юрлиц/ИП (Альфа-Бизнес Онлайн) — отдельный
# формат от alfabank_pdf.py (тот — только для физлиц: другая шапка, другая
# структура строки операции). Здесь полноценная таблица с рамками (Дата/Номер/
# Дебет/Кредит/Контрагент/Банк/Назначение платежа/Код дебитор/Документ), поэтому
# так же, как у ВТБ (см. vtb_pdf.py), разбираем через pdfplumber.extract_table()
# по границам ячеек, а не регэкспом по тексту — иначе Дебет/Кредит (обе колонки
# просто "число" в потоке текста) неразличимы.
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
ACCOUNT_RE = re.compile(r"Счёт:\s*([\d ]+?)\s+Документ")
PERIOD_RE = re.compile(r"Период:\s*c\s*(\d{2}\.\d{2}\.\d{4})\s*по\s*(\d{2}\.\d{2}\.\d{4})")
OPENING_RE = re.compile(r"([\d ]+,\d{2})\s*RUR\s+[\d ]+,\d{2}\s*RUR\s*\nОстаток входящий:")
CLOSING_RE = re.compile(r"([\d ]+,\d{2})\s*RUR\s+[\d ]+,\d{2}\s*RUR\s*\nОстаток исходящий:")
INN_IN_CELL_RE = re.compile(r"ИНН:\s*\d+")


def _parse_ru_date(s: str) -> date:
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


def _clean_amount(s: Optional[str]) -> Decimal:
    s = (s or "").replace(" ", "").replace("\xa0", "").replace(",", ".").strip()
    return Decimal(s) if s else Decimal("0")


def sniff(text: str) -> bool:
    return "Выписка по счёту" in text and "Владелец счёта" in text and "Обороты по дебету" in text


def parse(pdf_bytes: bytes) -> ParsedStatement:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = pdf.pages[0].extract_text() or ""
        rows: List[list] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                rows.extend(table)
    return parse_rows(text, rows)


def parse_rows(text: str, rows: List[list]) -> ParsedStatement:
    m_account = ACCOUNT_RE.search(text)
    account_number = m_account.group(1).replace(" ", "") if m_account else None

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

    dedup = DedupKeyBuilder("alfabank_business_pdf", account_number)
    transactions = []
    for row in rows:
        if not row or not row[0] or not DATE_RE.match((row[0] or "").strip()):
            continue
        date_odds = _parse_ru_date(row[0].strip())
        number = (row[1] or "").strip()
        debet = _clean_amount(row[2] if len(row) > 2 else None)
        kredit = _clean_amount(row[3] if len(row) > 3 else None)
        contragent_cell = " ".join((row[4] or "").split("\n")) if len(row) > 4 else ""
        purpose = " ".join((row[6] or "").split()) if len(row) > 6 else ""

        is_expense = debet > 0
        amount = debet if is_expense else kredit
        if amount == 0:
            continue

        m_inn = INN_IN_CELL_RE.search(contragent_cell)
        counterparty_name = contragent_cell[: m_inn.start()].strip() if m_inn else contragent_cell.strip()

        transactions.append(
            {
                "external_ref": dedup.build(date_odds, amount, purpose, extra=number),
                "date_odds": date_odds,
                "type": "expense" if is_expense else "income",
                "amount": amount,
                "comment": purpose or None,
                "counterparty_name": counterparty_name or None,
                "is_financing": False,
            }
        )

    if not transactions:
        raise StatementParseError("В выписке Альфа-Бизнес не найдено ни одной операции")

    return ParsedStatement(
        bank="alfabank_business",
        account_number=account_number,
        period_from=period_from,
        period_to=period_to,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        closing_balance_date=period_to,
        transactions=transactions,
    )
