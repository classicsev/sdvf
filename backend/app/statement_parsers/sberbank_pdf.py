import io
import re
from datetime import date
from decimal import Decimal

import pdfplumber

from app.statement_parsers.base import DedupKeyBuilder, ParsedStatement, StatementParseError

# Сбербанк «Индивидуальная выписка по платёжному счёту» (физлицо) — две строки на
# операцию: 1) дата, время, категория (жирным), сумма (без знака = списание, "+" = приход
# — обратная от Т-Банка конвенция, сверено на реальном документе); 2) дата обработки, код
# авторизации, описание (может переноситься ещё на 1-2 строки). Нет ни одного поля с
# остатком по счёту — только "Пополнение"/"Списание" за весь период.
LINE_A = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+\d{2}:\d{2}\s+(.+?)\s+([+-]?[\d\s\xa0]+,\d{2})$")
LINE_B = re.compile(r"^\d{2}\.\d{2}\.\d{4}\s+\d{4,8}\s+(.+)$")

ACCOUNT_RE = re.compile(r"Номер счёта\s+((?:\d[\d ]*\d|\d))\s+(?:Карты|Списание)")
PERIOD_RE = re.compile(r"За период (\d{2}\.\d{2}\.\d{4})\s*[—-]\s*(\d{2}\.\d{2}\.\d{4})")

BOILERPLATE_MARKERS = (
    "www.sberbank.ru",
    "Индивидуальная выписка",
    "За период",
    "ИТОГО ПО ОПЕРАЦИЯМ",
    "Владелец счёта",
    "Пополнение +",
    "Номер счёта",
    "Списание",
    "Карты, привязанные",
    "Валюта",
    "Дата открытия счёта",
    "Дата закрытия счёта",
    "Дополнительно заполненные",
    "Тип операции",
    "Расшифровка операций",
    "ДАТА ОПЕРАЦИИ",
    "Дата обработки",
    "Продолжение на следующей странице",
    "Для проверки подлинности",
    "Зайдите в приложение",
    "Нажмите кнопку",
    "Получите документ",
    "Действителен",
    "Предоставляя QR-код",
    "Страница",
)


def _is_boilerplate(line: str) -> bool:
    return any(marker in line for marker in BOILERPLATE_MARKERS)


def _parse_ru_date(s: str) -> date:
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


def _clean_amount(s: str) -> Decimal:
    return Decimal(s.replace(" ", "").replace("\xa0", "").replace(",", ".").lstrip("+"))


def sniff(text: str) -> bool:
    return "Индивидуальная выписка по платёжному счёту" in text


def parse(pdf_bytes: bytes) -> ParsedStatement:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return parse_text(text)


def parse_text(text: str) -> ParsedStatement:
    m_account = ACCOUNT_RE.search(text)
    account_number = m_account.group(1).replace(" ", "") if m_account else None

    period_from = period_to = None
    m_period = PERIOD_RE.search(text)
    if m_period:
        period_from = _parse_ru_date(m_period.group(1))
        period_to = _parse_ru_date(m_period.group(2))

    dedup = DedupKeyBuilder("sberbank_pdf", account_number)
    transactions = []
    lines = [l for l in text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        ma = LINE_A.match(line)
        if not ma or _is_boilerplate(line):
            i += 1
            continue
        date_s, category, amount_s = ma.groups()
        date_odds = _parse_ru_date(date_s)
        is_income = amount_s.strip().startswith("+")
        amount = _clean_amount(amount_s)
        i += 1

        desc_parts = []
        auth_code = ""
        if i < len(lines):
            mb = LINE_B.match(lines[i].strip())
            if mb and not _is_boilerplate(lines[i]):
                auth_code = lines[i].strip().split()[1]
                desc_parts.append(mb.group(1).strip())
                i += 1
                while i < len(lines) and not LINE_A.match(lines[i].strip()) and not _is_boilerplate(lines[i]):
                    desc_parts.append(lines[i].strip())
                    i += 1

        description = (category + (". " + " ".join(desc_parts) if desc_parts else "")).strip()
        tx_type = "income" if is_income else "expense"
        transactions.append(
            {
                "external_ref": dedup.build(date_odds, amount, description, extra=auth_code),
                "date_odds": date_odds,
                "type": tx_type,
                "amount": amount,
                "comment": description or None,
                "counterparty_name": None,
                "is_financing": False,
            }
        )

    if not transactions:
        raise StatementParseError("В выписке Сбербанка не найдено ни одной операции")

    return ParsedStatement(
        bank="sberbank",
        account_number=account_number,
        period_from=period_from,
        period_to=period_to,
        transactions=transactions,
    )
