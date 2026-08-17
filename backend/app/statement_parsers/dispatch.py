import io

import pdfplumber

from app.statement_parsers import alfabank_pdf, sberbank_pdf, tbank_pdf, vtb_pdf
from app.statement_parsers.base import ParsedStatement, StatementParseError

# Порядок проверки важен только в теории — сигнатуры (sniff) банков не пересекаются
# на реальных документах, но T-Bank/Sber проверяем раньше ВТБ/Альфы, т.к. их sniff
# строже (два конкретных маркера, а не один общий).
_PARSERS = [tbank_pdf, sberbank_pdf, alfabank_pdf, vtb_pdf]


def detect_and_parse(pdf_bytes: bytes) -> ParsedStatement:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:2])
    except Exception as exc:
        raise StatementParseError(f"Не удалось прочитать PDF: {exc}") from exc

    for module in _PARSERS:
        if module.sniff(text):
            return module.parse(pdf_bytes)

    raise StatementParseError(
        "Не удалось распознать банк по файлу. Сейчас поддерживаются справки/выписки "
        "Т-Банка, Сбербанка, Альфа-Банка и ВТБ для физлиц."
    )
