from datetime import date
from decimal import Decimal

import pytest

from app.statement_parsers import StatementParseError, alfabank_pdf, sberbank_pdf, tbank_pdf, vtb_pdf
from app.statement_parsers.dispatch import _PARSERS

# Синтетические тексты ниже воспроизводят реальную структуру справок/выписок
# (сверено на настоящих документах Т-Банка/Сбербанка/Альфа-Банка/ВТБ — контрольные
# суммы сходились день-в-день), но с вымышленными ФИО/счетами/суммами — реальные
# документы пользователя в репозиторий не попадают.

TBANK_TEXT = """АКЦИОНЕРНОЕ ОБЩЕСТВО «ТБАНК»
Справка о движении средств
Исх. № abc123 15.03.2026
Иванов Иван Иванович
О продукте
Номер лицевого счета: 40817810000000000001
Сумма доступного остатка на 15.03.2026: 5 000.00 ₽
Движение средств за период с 01.01.2026 по 15.03.2026
Дата и время Дата Сумма в валюте Сумма операции Описание Номер
операции списания операции в валюте карты операции карты
10.03.2026 10.03.2026 -500.00 ₽ -500.00 ₽ Оплата в MAGAZIN 1234
09:00 09:01 MOSCOW RUS
05.03.2026 05.03.2026 +10 000.00 ₽ +10 000.00 ₽ Пополнение счета —
08:00 08:00
"""

SBERBANK_TEXT = """900 www.sberbank.ru Заказано в СберБанк Онлайн
Индивидуальная выписка по платёжному счёту
За период 01.01.2026 — 15.03.2026
ИТОГО ПО ОПЕРАЦИЯМ ЗА ПЕРИОД:
Владелец счёта
Иванов Иван Иванович
Пополнение +10 000,00
Номер счёта 40817 810 0 0000 0000002 Списание 500,00
Карты, привязанные к счёту МИР •• 1111
Валюта Российский рубль
Дата открытия счёта 01.01.2020
ДАТА ОПЕРАЦИИ (МСК) КАТЕГОРИЯ СУММА В ВАЛЮТЕ СЧЁТА
Дата обработки1 Описание операции Сумма в валюте
10.03.2026 09:00 Перевод с карты 500,00
10.03.2026 123456 Перевод для П. Петр Петрович. Операция по счету ****0002
05.03.2026 08:00 Перевод СБП +10 000,00
05.03.2026 654321 Перевод из Ozon Bank (Ozon). Операция по счету ****0002
"""

ALFABANK_TEXT = """Выписка по счету
За период с 01.01.2026 по 15.03.2026
Номер счета 40817810000000000003
Дата открытия счета 01.01.2020 Входящий остаток 100,00 RUR
Валюта счета RUR Поступления 10 000,00 RUR
Дата формирования 15.03.2026 Расходы 500,00 RUR
выписки
Исходящий остаток 9 600,00 RUR
Операции по счету
Дата проводки Код операции Описание Сумма
в валюте счета
10.03.2026 C000000001 Перевод денежных средств -500,00 RUR
05.03.2026 C000000002 Перевод собственных средств от деятельности ИП 10 000,00 RUR
"""

VTB_TEXT = """Иванов Иван Иванович
Номер счёта 40817810000000000004 (RUB)
Период выписки 01.01.2026 - 15.03.2026
Наименование получателя/Отправителя
Баланс на начало периода 100.00 RUB Поступления 10000.00 RUB
Баланс на конец периода 9600.00 RUB Расходные операции 500.00 RUB
"""

VTB_ROWS = [
    ["Операции по счёту"],
    ["Дата и время\nоперации", "Дата обработки\nбанком", "Сумма операции в\nвалюте операции",
     "Сумма операции в валюте счета/карты", None, "Описание операции", "Наименование\nполучателя/\nОтправителя"],
    [None, None, None, "Приход", "Расход", None, None],
    ["10.03.2026", "10.03.2026", "-500.00 RUB", "0.00 RUB", "-500.00 RUB", "Переводы через СБП.", "Петр Петрович"],
    ["05.03.2026", "05.03.2026", "10000.00 RUB", "10000.00 RUB", "0.00 RUB", "Внутри ВТБ.", "Иванов Петр\nИванович"],
]


def test_tbank_parses_amounts_dates_and_closing_balance():
    stmt = tbank_pdf.parse_text(TBANK_TEXT)
    assert stmt.bank == "tbank"
    assert stmt.account_number == "40817810000000000001"
    assert stmt.period_from == date(2026, 1, 1)
    assert stmt.period_to == date(2026, 3, 15)
    assert stmt.closing_balance == Decimal("5000.00")
    assert stmt.closing_balance_date == date(2026, 3, 15)
    assert len(stmt.transactions) == 2
    expense, income = stmt.transactions
    assert expense["type"] == "expense"
    assert expense["amount"] == Decimal("500.00")
    assert expense["comment"] == "Оплата в MAGAZIN MOSCOW RUS"
    assert income["type"] == "income"
    assert income["amount"] == Decimal("10000.00")


def test_tbank_rejects_document_with_no_operations():
    with pytest.raises(StatementParseError):
        tbank_pdf.parse_text("Справка о движении средств\nНомер лицевого счета: 1\nСумма доступного остатка на 01.01.2026: 0.00 ₽")


def test_sberbank_uses_leading_plus_for_income_not_positive_sign():
    # Ключевая особенность Сбера: сумма БЕЗ знака = расход, "+"= приход (обратная
    # конвенция от Т-Банка, где расход показан явным минусом) — сверено на реальном
    # документе (см. HANDOVER/переписку), тест защищает именно эту инверсию.
    stmt = sberbank_pdf.parse_text(SBERBANK_TEXT)
    assert stmt.account_number == "40817810000000000002"
    assert len(stmt.transactions) == 2
    expense, income = stmt.transactions
    assert expense["type"] == "expense"
    assert expense["amount"] == Decimal("500.00")
    assert income["type"] == "income"
    assert income["amount"] == Decimal("10000.00")
    # У Сбера в этом документе нет ни одного поля с остатком по счёту.
    assert stmt.opening_balance is None
    assert stmt.closing_balance is None


def test_alfabank_reads_opening_and_closing_balance():
    stmt = alfabank_pdf.parse_text(ALFABANK_TEXT)
    assert stmt.account_number == "40817810000000000003"
    assert stmt.opening_balance == Decimal("100.00")
    assert stmt.closing_balance == Decimal("9600.00")
    assert len(stmt.transactions) == 2
    expense, income = stmt.transactions
    assert expense["amount"] == Decimal("500.00") and expense["type"] == "expense"
    assert income["amount"] == Decimal("10000.00") and income["type"] == "income"


def test_vtb_parses_table_rows_and_counterparty_column():
    stmt = vtb_pdf.parse_rows(VTB_TEXT, VTB_ROWS)
    assert stmt.account_number == "40817810000000000004"
    assert stmt.opening_balance == Decimal("100.00")
    assert stmt.closing_balance == Decimal("9600.00")
    assert len(stmt.transactions) == 2
    expense, income = stmt.transactions
    assert expense["type"] == "expense" and expense["amount"] == Decimal("500.00")
    assert expense["counterparty_name"] == "Петр Петрович"
    assert income["type"] == "income" and income["amount"] == Decimal("10000.00")
    assert income["counterparty_name"] == "Иванов Петр Иванович"


def test_dedup_key_is_deterministic_and_unique_for_repeated_identical_rows():
    # Один и тот же файл, распарсенный дважды, должен давать одинаковые
    # external_ref (иначе повторная загрузка того же документа задвоит операции);
    # а одинаковые (дата, сумма, описание) внутри одного документа не должны
    # схлопнуться в один и тот же ключ.
    stmt1 = tbank_pdf.parse_text(TBANK_TEXT)
    stmt2 = tbank_pdf.parse_text(TBANK_TEXT)
    assert [t["external_ref"] for t in stmt1.transactions] == [t["external_ref"] for t in stmt2.transactions]

    text_with_dupe = TBANK_TEXT + "10.03.2026 10.03.2026 -500.00 ₽ -500.00 ₽ Оплата в MAGAZIN 1234\n09:00 09:01 MOSCOW RUS\n"
    stmt3 = tbank_pdf.parse_text(text_with_dupe)
    refs = [t["external_ref"] for t in stmt3.transactions]
    assert len(refs) == len(set(refs))


@pytest.mark.parametrize(
    "text,expected_bank",
    [(TBANK_TEXT, "tbank"), (SBERBANK_TEXT, "sberbank"), (ALFABANK_TEXT, "alfabank")],
)
def test_sniff_uniquely_identifies_each_bank(text, expected_bank):
    matches = [module.sniff(text) for module in _PARSERS]
    assert sum(matches) == 1
    matched_module = _PARSERS[matches.index(True)]
    assert matched_module.parse_text(text).bank == expected_bank
