import io

import pdfplumber

from app.statement_parsers import (
    alfabank_business_pdf,
    alfabank_pdf,
    client_bank_1c,
    sberbank_pdf,
    tbank_pdf,
    vtb_pdf,
)
from app.statement_parsers.base import ParsedStatement, StatementParseError

# Порядок проверки важен не только в теории здесь: sniff личного alfabank_pdf
# ловит любой документ с подстрокой "АО «АЛЬФА-БАНК»" в шапке — а она есть и в
# выписке Альфа-Бизнес для юрлиц/ИП. alfabank_business_pdf (три конкретных
# маркера, включая "Обороты по дебету", которых в личной выписке нет) должен
# проверяться раньше alfabank_pdf, иначе бизнес-выписка ошибочно уйдёт в
# личный парсер.
_PARSERS = [tbank_pdf, sberbank_pdf, alfabank_business_pdf, alfabank_pdf, vtb_pdf]


def detect_and_parse(raw_bytes: bytes) -> ParsedStatement:
    # 1С:Клиент-Банк — обычный текстовый файл (не PDF), проверяем и разбираем
    # его в первую очередь, до попытки открыть содержимое как PDF ниже.
    if client_bank_1c.sniff_bytes(raw_bytes):
        return client_bank_1c.parse(raw_bytes)

    try:
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:2])
    except Exception as exc:
        raise StatementParseError(f"Не удалось прочитать файл: {exc}") from exc

    for module in _PARSERS:
        if module.sniff(text):
            return module.parse(raw_bytes)

    raise StatementParseError(
        "Не удалось распознать банк по файлу. Сейчас поддерживаются справки/выписки "
        "Т-Банка, Сбербанка, Альфа-Банка (физлица и Альфа-Бизнес) и ВТБ, а также файлы "
        "выгрузки 1С:Клиент-Банк (для юрлиц/ИП)."
    )
