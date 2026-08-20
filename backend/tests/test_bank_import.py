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


def test_api_import_does_not_use_semantic_dedup(db_session):
    """Защита по смыслу (счёт+дата+сумма+тип) применяется только к
    external_ref с префиксом "statement:" — синк по API (external_ref
    вида "alfa:<uuid>"/"tbank:<id>") продолжает дедупиться строго по
    external_ref, как и раньше, даже если по счёту/дате/сумме/типу
    "похожая" операция уже есть (например, два реальных перевода на
    одну и ту же сумму в один день — это не дубли)."""
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
