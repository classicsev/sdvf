from datetime import date

from app.bank_import import import_mapped_transactions
from app.models import Transaction

from .conftest import make_account, make_category, make_company, make_user


def _mapped(external_ref, date_odds, amount, tx_type, comment="Оплата по договору"):
    return {
        "external_ref": external_ref,
        "date_odds": date_odds,
        "type": tx_type,
        "amount": amount,
        "comment": comment,
        "counterparty_name": None,
        "is_financing": False,
    }


def test_statement_import_skips_transaction_already_synced_via_api(db_session):
    """Одна и та же реальная операция могла уже прийти по API-синку
    (external_ref="alfa:<uuid>") — импорт той же операции из выписки
    (external_ref="statement:...") не должен создать дубль, хотя
    external_ref у них никогда не совпадёт буквально."""
    company = make_company(db_session)
    user = make_user(db_session, company_id=company.id)
    account = make_account(db_session, company_id=company.id)
    category = make_category(db_session, company_id=company.id, tx_type="income")

    existing = Transaction(
        company_id=company.id,
        date_odds=date(2026, 5, 12),
        account_id=account.id,
        category_id=category.id,
        type="income",
        amount=15000,
        currency=account.currency,
        amount_rub=15000,
        bank_payment_purpose="Оплата по договору №1",
        external_ref="alfa:11111111-2222-3333-4444-555555555555",
        created_by=user.id,
    )
    db_session.add(existing)
    db_session.commit()

    mapped_ops = [
        _mapped(
            "statement:alfabank_business:deadbeefdeadbeefdead",
            date(2026, 5, 12),
            15000,
            "income",
        )
    ]

    result = import_mapped_transactions(db_session, user, company.id, account, mapped_ops)

    assert result["created"] == 0
    assert result["skipped_duplicate"] == 1
    assert db_session.query(Transaction).count() == 1


def test_statement_import_creates_transaction_with_no_api_match(db_session):
    """Операция из выписки без совпадения по (счёт, дата, сумма, тип) среди
    существующих операций — импортируется как обычно, защита от задвоения
    не должна блокировать реально новые операции."""
    company = make_company(db_session)
    user = make_user(db_session, company_id=company.id)
    account = make_account(db_session, company_id=company.id)

    mapped_ops = [
        _mapped(
            "statement:alfabank_business:deadbeefdeadbeefdead",
            date(2026, 5, 12),
            15000,
            "income",
        )
    ]

    result = import_mapped_transactions(db_session, user, company.id, account, mapped_ops)
    db_session.commit()

    assert result["created"] == 1
    assert result["skipped_duplicate"] == 0
    assert db_session.query(Transaction).count() == 1


def test_api_import_does_not_dedup_against_other_api_transactions(db_session):
    """Защита по смыслу (счёт+дата+сумма+тип) для операции из API ищет
    совпадение только среди операций ИЗ ВЫПИСКИ (external_ref
    "statement:..."), не среди других API-операций — синк по API
    продолжает дедупиться строго по external_ref против ДРУГИХ
    API-операций, даже если по счёту/дате/сумме/типу "похожая" операция
    уже есть (например, два реальных перевода на одну и ту же сумму в
    один день — это не дубли)."""
    company = make_company(db_session)
    user = make_user(db_session, company_id=company.id)
    account = make_account(db_session, company_id=company.id)
    category = make_category(db_session, company_id=company.id, tx_type="income")

    existing = Transaction(
        company_id=company.id,
        date_odds=date(2026, 5, 12),
        account_id=account.id,
        category_id=category.id,
        type="income",
        amount=15000,
        currency=account.currency,
        amount_rub=15000,
        bank_payment_purpose="Оплата по договору №1",
        external_ref="alfa:11111111-2222-3333-4444-555555555555",
        created_by=user.id,
    )
    db_session.add(existing)
    db_session.commit()

    mapped_ops = [
        _mapped(
            "alfa:66666666-7777-8888-9999-000000000000",
            date(2026, 5, 12),
            15000,
            "income",
        )
    ]

    result = import_mapped_transactions(db_session, user, company.id, account, mapped_ops)
    db_session.commit()

    assert result["created"] == 1
    assert result["skipped_duplicate"] == 0
    assert db_session.query(Transaction).count() == 2


def test_api_import_skips_transaction_already_imported_from_statement(db_session):
    """Обратное направление задвоения (реальный баг ТД Щёлоковъ,
    03.09.2026): операция уже была загружена из PDF-выписки
    (external_ref "statement:...") ДО того, как счёт подключили к
    API-синку. Когда синк по API позже подтягивает тот же исторический
    период, он не должен создать дубль — раньше защита работала только
    в обратную сторону (выписка после API), поэтому такой сценарий
    реально задвоил 588 операций ТД Щёлоковъ."""
    company = make_company(db_session)
    user = make_user(db_session, company_id=company.id)
    account = make_account(db_session, company_id=company.id)
    category = make_category(db_session, company_id=company.id, tx_type="income")

    existing = Transaction(
        company_id=company.id,
        date_odds=date(2026, 5, 12),
        account_id=account.id,
        category_id=category.id,
        type="income",
        amount=15000,
        currency=account.currency,
        amount_rub=15000,
        bank_payment_purpose="Оплата по договору №1",
        external_ref="statement:alfabank_business_pdf:deadbeefdeadbeefdead",
        created_by=user.id,
    )
    db_session.add(existing)
    db_session.commit()

    mapped_ops = [
        _mapped(
            "alfa:66666666-7777-8888-9999-000000000000",
            date(2026, 5, 12),
            15000,
            "income",
        )
    ]

    result = import_mapped_transactions(db_session, user, company.id, account, mapped_ops)
    db_session.commit()

    assert result["created"] == 0
    assert result["skipped_duplicate"] == 1
    assert db_session.query(Transaction).count() == 1


def test_semantic_dedup_tolerates_one_day_date_offset(db_session):
    """У ТД Щёлоковъ разбор PDF-выписки Альфа-Бизнес систематически
    показывал дату операции на 1 день позже, чем та же операция в API
    (дата проводки vs дата исполнения) — 9 реальных дублей 03.09.2026
    не поймались бы точным равенством дат."""
    company = make_company(db_session)
    user = make_user(db_session, company_id=company.id)
    account = make_account(db_session, company_id=company.id)
    category = make_category(db_session, company_id=company.id, tx_type="income")

    existing = Transaction(
        company_id=company.id,
        date_odds=date(2026, 5, 24),
        account_id=account.id,
        category_id=category.id,
        type="income",
        amount=21000,
        currency=account.currency,
        amount_rub=21000,
        bank_payment_purpose="ОПЛАТА ПО ДОГОВОРУ ТД-257-2025",
        external_ref="alfa:11111111-2222-3333-4444-555555555555",
        created_by=user.id,
    )
    db_session.add(existing)
    db_session.commit()

    mapped_ops = [
        _mapped(
            "statement:alfabank_business_pdf:aaaaaaaaaaaaaaaaaaaa",
            date(2026, 5, 25),
            21000,
            "income",
        )
    ]

    result = import_mapped_transactions(db_session, user, company.id, account, mapped_ops)
    db_session.commit()

    assert result["created"] == 0
    assert result["skipped_duplicate"] == 1
    assert db_session.query(Transaction).count() == 1


def test_semantic_dedup_does_not_match_beyond_one_day(db_session):
    """Допуск по дате ограничен ±1 днём — операция двумя днями позже с
    той же суммой/типом должна создаваться как отдельная, не считаться
    дублем (иначе риск ложного схлопывания разных реальных операций)."""
    company = make_company(db_session)
    user = make_user(db_session, company_id=company.id)
    account = make_account(db_session, company_id=company.id)
    category = make_category(db_session, company_id=company.id, tx_type="income")

    existing = Transaction(
        company_id=company.id,
        date_odds=date(2026, 5, 24),
        account_id=account.id,
        category_id=category.id,
        type="income",
        amount=21000,
        currency=account.currency,
        amount_rub=21000,
        bank_payment_purpose="ОПЛАТА ПО ДОГОВОРУ ТД-257-2025",
        external_ref="alfa:11111111-2222-3333-4444-555555555555",
        created_by=user.id,
    )
    db_session.add(existing)
    db_session.commit()

    mapped_ops = [
        _mapped(
            "statement:alfabank_business_pdf:bbbbbbbbbbbbbbbbbbbb",
            date(2026, 5, 26),
            21000,
            "income",
        )
    ]

    result = import_mapped_transactions(db_session, user, company.id, account, mapped_ops)
    db_session.commit()

    assert result["created"] == 1
    assert result["skipped_duplicate"] == 0
    assert db_session.query(Transaction).count() == 2


def test_api_import_skips_transaction_already_entered_manually(db_session):
    """У ТД Щёлоковъ одна реальная оплата была занесена вручную через
    интерфейс (external_ref IS NULL) ещё до подключения API — синк
    задвоил и её, потому что защита проверяла только external_ref
    "statement:...", не учитывая ручной ввод."""
    company = make_company(db_session)
    user = make_user(db_session, company_id=company.id)
    account = make_account(db_session, company_id=company.id)
    category = make_category(db_session, company_id=company.id, tx_type="income")

    existing = Transaction(
        company_id=company.id,
        date_odds=date(2026, 8, 24),
        account_id=account.id,
        category_id=category.id,
        type="income",
        amount=61500,
        currency=account.currency,
        amount_rub=61500,
        bank_payment_purpose=None,
        comment="оплата ТД-939 от 8.08",
        external_ref=None,
        created_by=user.id,
    )
    db_session.add(existing)
    db_session.commit()

    mapped_ops = [_mapped("alfa:26cda125-1ea1-30d9-bb5b-4a4295e5a26e", date(2026, 8, 24), 61500, "income")]

    result = import_mapped_transactions(db_session, user, company.id, account, mapped_ops)
    db_session.commit()

    assert result["created"] == 0
    assert result["skipped_duplicate"] == 1
    assert db_session.query(Transaction).count() == 1
