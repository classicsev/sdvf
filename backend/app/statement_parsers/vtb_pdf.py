import io
import re
from datetime import date
from decimal import Decimal
from typing import List

import pdfplumber

from app.statement_parsers.base import DedupKeyBuilder, ParsedStatement, StatementParseError

# ВТБ «Выписка по счёту» (физлицо) — единственный из четырёх банков, где в тексте
# нет разделительных пробелов между колонками (описание/контрагент съезжаются с
# соседними ячейками при построчном чтении текста), поэтому парсим через
# pdfplumber.extract_table() по линиям сетки, а не регуляркой по тексту.
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
ACCOUNT_RE = re.compile(r"Номер счёта\s+(\d+)")
PERIOD_RE = re.compile(r"Период выписки\s+(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})")
OPENING_RE = re.compile(r"Баланс на начало периода\s+([\d.]+)\s*RUB")
CLOSING_RE = re.compile(r"Баланс на конец периода\s+([\d.]+)\s*RUB")


def _parse_ru_date(s: str) -> date:
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


def _clean_amount(s: str) -> Decimal:
    return Decimal((s or "0").replace("RUB", "").replace(" ", "").replace("\xa0", "").strip() or "0")


def sniff(text: str) -> bool:
    return "Период выписки" in text and "Наименование" in text and "получателя" in text


def parse(pdf_bytes: bytes) -> ParsedStatement:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        rows: List[list] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                rows.extend(table)
    return parse_rows(text, rows)


def parse_rows(text: str, rows: List[list]) -> ParsedStatement:
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

    dedup = DedupKeyBuilder("vtb_pdf", account_number)
    transactions = []
    for row in rows:
        if not row or not row[0] or not DATE_RE.match(row[0].strip()):
            continue
        date_odds = _parse_ru_date(row[0].strip())
        prihod = _clean_amount(row[3] if len(row) > 3 else None)
        rashod = _clean_amount(row[4] if len(row) > 4 else None)
        description = " ".join((row[5] or "").split()) if len(row) > 5 else ""
        counterparty_name = " ".join((row[6] or "").split()) if len(row) > 6 else None

        is_income = prihod > 0
        amount = prihod if is_income else abs(rashod)
        if amount == 0:
            continue

        transactions.append(
            {
                "external_ref": dedup.build(date_odds, amount, description, extra=counterparty_name or ""),
                "date_odds": date_odds,
                "type": "income" if is_income else "expense",
                "amount": amount,
                "comment": description or None,
                "counterparty_name": counterparty_name or None,
                "is_financing": False,
            }
        )

    if not transactions:
        raise StatementParseError("В выписке ВТБ не найдено ни одной операции")

    return ParsedStatement(
        bank="vtb",
        account_number=account_number,
        period_from=period_from,
        period_to=period_to,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        closing_balance_date=period_to,
        transactions=transactions,
    )
