import io
import re
from datetime import date
from decimal import Decimal

import pdfplumber

from app.statement_parsers.base import DedupKeyBuilder, ParsedStatement, StatementParseError

# Т-Банк «Справка о движении средств» (физлицо, без API) — два физических текстовых ряда
# на операцию: 1) дата операции, дата списания, сумма (х2, дублируется — валюта операции
# всегда совпадает с валютой карты), начало описания, номер карты/«—»; 2) время операции,
# время списания, продолжение описания. Формат сверен на реальном документе — контрольная
# сумма "Пополнения"/"Расходы" из футера справки сходится с суммой распарсенных операций
# день-в-день (см. backend/tests/test_statement_parsers.py).
LINE_A = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s+\d{2}\.\d{2}\.\d{4}\s+([+-][\d\s\xa0]+\.\d{2})\s*₽\s+"
    r"[+-][\d\s\xa0]+\.\d{2}\s*₽\s+(.+)$"
)
LINE_B = re.compile(r"^\d{2}:\d{2}\s+\d{2}:\d{2}\s*(.*)$")

ACCOUNT_RE = re.compile(r"Номер лицевого счета:\s*(\d+)")
BALANCE_RE = re.compile(r"Сумма доступного остатка на (\d{2}\.\d{2}\.\d{4}):\s*([\d\s\xa0]+\.\d{2})\s*₽")
PERIOD_RE = re.compile(r"за период с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})")


def _parse_ru_date(s: str) -> date:
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


def _clean_amount(s: str) -> Decimal:
    return Decimal(s.replace(" ", "").replace("\xa0", ""))


def sniff(text: str) -> bool:
    return "Номер лицевого счета" in text and "Сумма доступного остатка" in text


def parse(pdf_bytes: bytes) -> ParsedStatement:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return parse_text(text)


def parse_text(text: str) -> ParsedStatement:
    m_account = ACCOUNT_RE.search(text)
    account_number = m_account.group(1) if m_account else None

    closing_balance = None
    closing_balance_date = None
    m_balance = BALANCE_RE.search(text)
    if m_balance:
        closing_balance_date = _parse_ru_date(m_balance.group(1))
        closing_balance = _clean_amount(m_balance.group(2))

    period_from = period_to = None
    m_period = PERIOD_RE.search(text)
    if m_period:
        period_from = _parse_ru_date(m_period.group(1))
        period_to = _parse_ru_date(m_period.group(2))

    dedup = DedupKeyBuilder("tbank_pdf", account_number)
    transactions = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ma = LINE_A.match(lines[i].strip())
        if not ma:
            i += 1
            continue
        date_s, amount_s, rest = ma.groups()
        date_odds = _parse_ru_date(date_s)
        amount = _clean_amount(amount_s)
        rest = rest.strip()
        parts = rest.rsplit(" ", 1)
        desc1, card = parts if len(parts) == 2 else (rest, "")
        i += 1
        desc2 = ""
        if i < len(lines):
            mb = LINE_B.match(lines[i].strip())
            if mb:
                desc2 = mb.group(1).strip()
                i += 1

        description = f"{desc1} {desc2}".strip()
        tx_type = "income" if amount >= 0 else "expense"
        transactions.append(
            {
                "external_ref": dedup.build(date_odds, abs(amount), description, extra=card),
                "date_odds": date_odds,
                "type": tx_type,
                "amount": abs(amount),
                "comment": description or None,
                "counterparty_name": None,
                "is_financing": False,
            }
        )

    if not transactions:
        raise StatementParseError("В справке Т-Банка не найдено ни одной операции")

    return ParsedStatement(
        bank="tbank",
        account_number=account_number,
        period_from=period_from,
        period_to=period_to,
        closing_balance=closing_balance,
        closing_balance_date=closing_balance_date,
        transactions=transactions,
    )
