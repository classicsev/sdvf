from datetime import date
from decimal import Decimal

from app.statement_parsers.base import DedupKeyBuilder, ParsedStatement, StatementParseError

# Формат "1С:Клиент-Банк" (1CClientBankExchange) — межбанковский стандарт обмена
# для бухгалтерских систем (не привязан к одному банку: Альфа-Бизнес Онлайн,
# Сбербанк Бизнес, Т-Банк и др. умеют его экспортировать для юрлиц/ИП), в
# отличие от остальных парсеров в этом пакете, которые разбирают PDF конкретного
# банка регэкспами по вёрстке. Текстовый файл построчно "Ключ=Значение", с
# заглавными служебными строками-маркерами разделов. Кодировка почти всегда
# Windows-1251 несмотря на заявленное поле "Кодировка=Windows" (которое на самом
# деле означает именно это, а не UTF-8) — но встречаются и UTF-8-экспорты, см.
# _decode.
#
# Каждая операция — блок между "СекцияДокумент=<тип>" и "КонецДокумента" (тип
# документа — платёжное поручение, банковский ордер и т.п. — не важен для нас,
# обрабатываются одинаково). Направление (приход/расход) определяется
# сравнением расчётного счёта плательщика с собственным счётом из шапки
# выписки (секция "СекцияРасчСчет"), а не по знаку суммы — она в файле всегда
# положительна для обеих сторон.

MAGIC = "1CClientBankExchange"


def sniff_bytes(data: bytes) -> bool:
    head = data[:128]
    for enc in ("cp1251", "utf-8-sig", "utf-8"):
        try:
            decoded = head.decode(enc)
        except UnicodeDecodeError:
            continue
        if decoded.lstrip("﻿").startswith(MAGIC):
            return True
    return False


def _decode(data: bytes) -> str:
    for enc in ("cp1251", "utf-8-sig", "utf-8"):
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        # Признак того, что кодировка выбрана верно — известное служебное поле
        # шапки читается как осмысленная кириллица, а не мусор/квадратики.
        if "ВерсияФормата" in text[:2000]:
            return text
    return data.decode("cp1251", errors="replace")


def _parse_ru_date(s: str) -> date:
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


def _parse_block(lines: list) -> dict:
    fields = {}
    for line in lines:
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip()
    return fields


def sniff(text: str) -> bool:
    return text.lstrip("﻿").startswith(MAGIC)


def parse(raw_bytes: bytes) -> ParsedStatement:
    return parse_text(_decode(raw_bytes))


def parse_text(text: str) -> ParsedStatement:
    lines = [l.rstrip("\r") for l in text.split("\n")]

    header_lines = []
    for line in lines:
        if line.startswith("СекцияРасчСчет") or line.startswith("СекцияДокумент"):
            break
        header_lines.append(line)
    header = _parse_block(header_lines)
    own_account = header.get("РасчСчет") or None
    period_from = _parse_ru_date(header["ДатаНачала"]) if header.get("ДатаНачала") else None
    period_to = _parse_ru_date(header["ДатаКонца"]) if header.get("ДатаКонца") else None

    opening_balance = closing_balance = None
    closing_balance_date = period_to
    acc_lines = []
    in_acc = False
    for line in lines:
        if line.startswith("СекцияРасчСчет"):
            in_acc = True
            continue
        if line.startswith("КонецРасчСчет"):
            break
        if in_acc:
            acc_lines.append(line)
    if acc_lines:
        acc_fields = _parse_block(acc_lines)
        if acc_fields.get("НачальныйОстаток"):
            opening_balance = Decimal(acc_fields["НачальныйОстаток"])
        if acc_fields.get("КонечныйОстаток"):
            closing_balance = Decimal(acc_fields["КонечныйОстаток"])
        if acc_fields.get("ДатаКонца"):
            closing_balance_date = _parse_ru_date(acc_fields["ДатаКонца"])

    dedup = DedupKeyBuilder("client_bank_1c", own_account)
    transactions = []

    doc_lines = []
    doc_type = None
    in_doc = False
    for line in lines:
        if line.startswith("СекцияДокумент="):
            in_doc = True
            doc_type = line.split("=", 1)[1].strip()
            doc_lines = []
            continue
        if line.startswith("КонецДокумента"):
            if in_doc:
                tx = _build_transaction(_parse_block(doc_lines), own_account, doc_type, dedup)
                if tx:
                    transactions.append(tx)
            in_doc = False
            continue
        if in_doc:
            doc_lines.append(line)

    if not transactions:
        raise StatementParseError("В файле выгрузки 1С-обмена не найдено ни одной операции")

    return ParsedStatement(
        bank="client_bank_1c",
        account_number=own_account,
        period_from=period_from,
        period_to=period_to,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        closing_balance_date=closing_balance_date,
        transactions=transactions,
    )


def _build_transaction(fields: dict, own_account, doc_type, dedup: DedupKeyBuilder):
    amount_s = fields.get("Сумма")
    if not amount_s:
        return None
    try:
        amount = abs(Decimal(amount_s))
    except Exception:
        return None

    payer_account = fields.get("ПлательщикРасчСчет") or fields.get("ПлательщикСчет")
    is_expense = payer_account is not None and payer_account == own_account

    date_field = "ДатаСписано" if is_expense else "ДатаПоступило"
    date_s = fields.get(date_field) or fields.get("Дата")
    if not date_s:
        return None
    try:
        date_odds = _parse_ru_date(date_s)
    except (ValueError, IndexError):
        return None

    purpose = fields.get("НазначениеПлатежа") or ""
    counterparty_name = fields.get("Получатель") if is_expense else fields.get("Плательщик")
    number = fields.get("Номер", "")

    return {
        "external_ref": dedup.build(date_odds, amount, purpose, extra=f"{doc_type}:{number}"),
        "date_odds": date_odds,
        "type": "expense" if is_expense else "income",
        "amount": amount,
        "comment": purpose or None,
        "counterparty_name": counterparty_name or None,
        "is_financing": False,
    }
