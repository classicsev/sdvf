from datetime import date
from decimal import Decimal

import pytest

from app.statement_parsers import (
    StatementParseError,
    alfabank_business_pdf,
    alfabank_pdf,
    client_bank_1c,
    sberbank_pdf,
    tbank_pdf,
    vtb_pdf,
)
from app.statement_parsers.dispatch import _PARSERS, detect_and_parse

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


CLIENT_BANK_1C_TEXT = """1CClientBankExchange
ВерсияФормата=1.03
Кодировка=Windows
Отправитель=Альфа-Бизнес Онлайн
Получатель=
ДатаСоздания=15.03.2026
ВремяСоздания=09:57:58
ДатаНачала=01.01.2026
ДатаКонца=15.03.2026
РасчСчет=40702810000000000005

СекцияРасчСчет
ДатаНачала=01.01.2026
ДатаКонца=15.03.2026
РасчСчет=40702810000000000005
НачальныйОстаток=100.00
ВсегоПоступило=10000.00
ВсегоСписано=500.00
КонечныйОстаток=9600.00
КонецРасчСчет

СекцияДокумент=Платежное поручение
Номер=1
Дата=10.03.2026
Сумма=500.00
ПлательщикСчет=40702810000000000005
ДатаСписано=10.03.2026
Плательщик=ООО "РОМАШКА"
ПлательщикИНН=1234567890
ПлательщикРасчСчет=40702810000000000005
ПолучательСчет=40702810000000000099
ДатаПоступило=
Получатель=ООО "ПОСТАВЩИК"
ПолучательИНН=9876543210
ПолучательРасчСчет=40702810000000000099
НазначениеПлатежа=Оплата по счету N 10 за товар
КонецДокумента

СекцияДокумент=Платежное поручение
Номер=2
Дата=05.03.2026
Сумма=10000.00
ПлательщикСчет=40702810000000000042
ДатаСписано=
Плательщик=ООО "ПОКУПАТЕЛЬ"
ПлательщикИНН=1112223330
ПлательщикРасчСчет=40702810000000000042
ПолучательСчет=40702810000000000005
ДатаПоступило=05.03.2026
Получатель=ООО "РОМАШКА"
ПолучательИНН=1234567890
ПолучательРасчСчет=40702810000000000005
НазначениеПлатежа=Оплата по договору N 5
КонецДокумента

КонецВыписки
"""


ALFABANK_BUSINESS_TEXT = """АО «АЛЬФА-БАНК»
ДО "Дальневосточный" в ФИЛИАЛ "ХАБАРОВСКИЙ" АО "АЛЬФА-БАНК"
690000, г.Владивосток, ул. Семеновская, д.26
Выписка по счёту
к/сч. 30101810800000000770 в ОКЦ № 2 ДГУ Банка России
БИК 040813770 ИНН 7728168971
Счёт: 40817 810 0 00000 000006 Документ передан в электронном виде
15.03.2026
Владелец счёта: ООО "РОМАШКА" Иванов Иван Иванович
Период: c 01.01.2026 по 15.03.2026 БИК: 040813770
Валюта счёта: Российский рубль Корр. 30101 810 8 00000 000770
ИНН: 1234567890 Адрес: 690000, г.Владивосток
100,00 RUR 10000,00 RUR
Остаток входящий: Обороты по дебету:
9600,00 RUR 500,00 RUR
Остаток исходящий: Обороты по кредиту:
31.12.2025
Дата предыдущей операции по счёту:
Контрагент Код
Дата Номер Дебет Кредит Назначение платежа Документ
Наименование, ИНН, КПП, счёт Банк (БИК, наименование) дебитор
"""

ALFABANK_BUSINESS_ROWS = [
    ["Дата", "Номер", "Дебет", "Кредит", "Контрагент", None, "Назначение платежа", "Код\nдебитор", "Документ"],
    [None, None, None, None, "Наименование, ИНН, КПП, счёт", "Банк (БИК, наименование)", None, None, None],
    [
        "10.03.2026",
        "1",
        "500,00",
        "",
        'ООО "ПОСТАВЩИК"\nИНН: 9998887770 КПП: 999888777\nСчёт: 40702810000000000099',
        "БИК: 044525593\nБанк: АО \"АЛЬФА-БАНК\" г Москва",
        "Оплата по счету N 10 за товар",
        "",
        "Платежное\nпоручение",
    ],
    [
        "05.03.2026",
        "2",
        "",
        "10000,00",
        'ООО "ПОКУПАТЕЛЬ"\nИНН: 1112223330\nСчёт: 40702810000000000042',
        "БИК: 044525225\nБанк: ПАО Сбербанк г Москва",
        "Оплата по договору N 5",
        "",
        "Платежное\nпоручение",
    ],
]


def test_alfabank_business_splits_debet_credit_by_table_column():
    stmt = alfabank_business_pdf.parse_rows(ALFABANK_BUSINESS_TEXT, ALFABANK_BUSINESS_ROWS)
    assert stmt.account_number == "40817810000000000006"
    assert stmt.period_from == date(2026, 1, 1)
    assert stmt.period_to == date(2026, 3, 15)
    assert stmt.opening_balance == Decimal("100.00")
    assert stmt.closing_balance == Decimal("9600.00")
    assert len(stmt.transactions) == 2
    expense, income = stmt.transactions
    assert expense["type"] == "expense" and expense["amount"] == Decimal("500.00")
    assert expense["counterparty_name"] == 'ООО "ПОСТАВЩИК"'
    assert expense["comment"] == "Оплата по счету N 10 за товар"
    assert income["type"] == "income" and income["amount"] == Decimal("10000.00")
    assert income["counterparty_name"] == 'ООО "ПОКУПАТЕЛЬ"'


def test_alfabank_business_sniff_wins_over_personal_alfabank_parser():
    # У обеих выписок в шапке встречается "АО «АЛЬФА-БАНК»" — sniff личного
    # парсера (alfabank_pdf) слишком общий и матчит и бизнес-выписку тоже.
    # alfabank_business_pdf должен стоять раньше в _PARSERS и перехватывать её
    # первым — иначе бизнес-выписка ошибочно уйдёт в парсер для физлиц.
    assert alfabank_pdf.sniff(ALFABANK_BUSINESS_TEXT) is True
    assert alfabank_business_pdf.sniff(ALFABANK_BUSINESS_TEXT) is True
    assert _PARSERS.index(alfabank_business_pdf) < _PARSERS.index(alfabank_pdf)


def test_client_bank_1c_reads_balances_and_splits_by_own_account():
    stmt = client_bank_1c.parse_text(CLIENT_BANK_1C_TEXT)
    assert stmt.account_number == "40702810000000000005"
    assert stmt.period_from == date(2026, 1, 1)
    assert stmt.period_to == date(2026, 3, 15)
    assert stmt.opening_balance == Decimal("100.00")
    assert stmt.closing_balance == Decimal("9600.00")
    assert len(stmt.transactions) == 2
    expense, income = stmt.transactions
    assert expense["type"] == "expense" and expense["amount"] == Decimal("500.00")
    assert expense["counterparty_name"] == "ООО \"ПОСТАВЩИК\""
    assert expense["comment"] == "Оплата по счету N 10 за товар"
    assert expense["date_odds"] == date(2026, 3, 10)
    assert income["type"] == "income" and income["amount"] == Decimal("10000.00")
    assert income["counterparty_name"] == "ООО \"ПОКУПАТЕЛЬ\""
    assert income["date_odds"] == date(2026, 3, 5)


def test_client_bank_1c_sniff_bytes_handles_cp1251_encoding():
    raw = CLIENT_BANK_1C_TEXT.encode("cp1251")
    assert client_bank_1c.sniff_bytes(raw) is True
    stmt = client_bank_1c.parse(raw)
    assert len(stmt.transactions) == 2


def test_client_bank_1c_sniff_bytes_rejects_pdf_and_other_banks():
    assert client_bank_1c.sniff_bytes(TBANK_TEXT.encode("utf-8")) is False
    assert client_bank_1c.sniff_bytes(b"%PDF-1.4 not a 1c file") is False


def test_detect_and_parse_routes_1c_exchange_file_before_pdf_attempt():
    # Байтовый sniff 1С-обмена должен сработать раньше попытки открыть файл как
    # PDF (иначе на текстовом файле упадём с "Не удалось прочитать файл").
    stmt = detect_and_parse(CLIENT_BANK_1C_TEXT.encode("cp1251"))
    assert stmt.bank == "client_bank_1c"


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
