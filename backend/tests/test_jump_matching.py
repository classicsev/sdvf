"""Юнит-тесты для jump_matching.py::match_payments — сопоставление выплат
Jump.Finance с уже существующими (пришедшими из банка) операциями по сумме+
дате, без прямой ссылки между системами."""

from datetime import date
from decimal import Decimal

from app.jump_matching import match_payments
from app.models import AutomationRule, Counterparty, RoleEnum, Transaction, TxTypeEnum
from tests.conftest import make_account, make_category, make_user


def _make_tx(db_session, account, category, amount, date_odds, external_ref="tbank:op-1", comment=None):
    tx = Transaction(
        company_id=account.company_id,
        date_odds=date_odds,
        account_id=account.id,
        category_id=category.id,
        type=TxTypeEnum.expense,
        amount=Decimal(str(amount)),
        currency="RUB",
        amount_rub=Decimal(str(amount)),
        external_ref=external_ref,
        comment=comment,
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    return tx


def _payment(payment_id="1", amount=5000, contractor_name="Иванов Иван Иванович", paid_at="2026-06-01T10:00:00+03:00", purpose="Оплата услуг"):
    return {
        "id": payment_id,
        "amount": amount,
        "amount_paid": amount - 100,
        "commission_bank": 0,
        "contractor": {"id": 42, "full_name": contractor_name, "short_name": "Иванов И.И."},
        "payment_purpose": purpose,
        "paid_at": paid_at,
        "created_at": paid_at,
    }


def test_match_sets_counterparty_and_category_via_automation_rule(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, company_id=admin.company_id)
    import_category = make_category(db_session, name="Импорт из банка (расход)", company_id=admin.company_id)
    contractor_category = make_category(db_session, name="Услуги подрядчиков", company_id=admin.company_id)

    db_session.add(
        AutomationRule(
            company_id=admin.company_id,
            condition_json={"field": "counterparty", "op": "contains", "value": "Иванов"},
            action_json={"set_category": contractor_category.id},
            is_active=True,
        )
    )
    db_session.commit()

    tx = _make_tx(db_session, account, import_category, 5000, date(2026, 6, 1))

    result = match_payments(db_session, admin, admin.company_id, account.id, [_payment()])
    assert result["matched"] == 1
    assert result["category_set_from_rule"] == 1
    assert result["category_set_from_default"] == 0

    db_session.refresh(tx)
    assert tx.category_id == contractor_category.id
    assert tx.jump_payment_id == "1"
    counterparty = db_session.query(Counterparty).filter(Counterparty.id == tx.counterparty_id).first()
    assert counterparty.name == "Иванов Иван Иванович"


def test_match_uses_counterparty_default_over_rule(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, company_id=admin.company_id)
    import_category = make_category(db_session, name="Импорт из банка (расход)", company_id=admin.company_id)
    rule_category = make_category(db_session, name="По правилу", company_id=admin.company_id)
    default_category = make_category(db_session, name="По умолчанию у контрагента", company_id=admin.company_id)

    db_session.add(
        AutomationRule(
            company_id=admin.company_id,
            condition_json={"field": "counterparty", "op": "contains", "value": "Иванов"},
            action_json={"set_category": rule_category.id},
            is_active=True,
        )
    )
    counterparty = Counterparty(
        company_id=admin.company_id, name="Иванов Иван Иванович", default_category_id=default_category.id
    )
    db_session.add(counterparty)
    db_session.commit()

    tx = _make_tx(db_session, account, import_category, 5000, date(2026, 6, 1))

    result = match_payments(db_session, admin, admin.company_id, account.id, [_payment()])
    assert result["matched"] == 1
    assert result["category_set_from_default"] == 1
    assert result["category_set_from_rule"] == 0

    db_session.refresh(tx)
    assert tx.category_id == default_category.id


def test_match_is_idempotent_on_rerun(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, company_id=admin.company_id)
    category = make_category(db_session, company_id=admin.company_id)
    tx = _make_tx(db_session, account, category, 5000, date(2026, 6, 1))

    payment = _payment()
    match_payments(db_session, admin, admin.company_id, account.id, [payment])
    db_session.refresh(tx)
    original_updated_at = tx.updated_at

    result = match_payments(db_session, admin, admin.company_id, account.id, [payment])
    assert result["matched"] == 0
    db_session.refresh(tx)
    assert tx.updated_at == original_updated_at


def test_match_skips_ambiguous_when_multiple_candidates(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, company_id=admin.company_id)
    category = make_category(db_session, company_id=admin.company_id)
    _make_tx(db_session, account, category, 5000, date(2026, 6, 1), external_ref="tbank:op-a")
    _make_tx(db_session, account, category, 5000, date(2026, 6, 1), external_ref="tbank:op-b")

    result = match_payments(db_session, admin, admin.company_id, account.id, [_payment()])
    assert result["matched"] == 0
    assert result["ambiguous"] == 1


def test_match_reports_unmatched_when_no_candidate(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, company_id=admin.company_id)

    result = match_payments(db_session, admin, admin.company_id, account.id, [_payment(amount=9999999)])
    assert result["matched"] == 0
    assert result["unmatched"] == 1


def test_match_falls_back_to_amount_plus_commission_bank(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, company_id=admin.company_id)
    category = make_category(db_session, company_id=admin.company_id)
    # В выписке банка сумма списания = amount + commission_bank
    tx = _make_tx(db_session, account, category, 5100, date(2026, 6, 1))

    payment = _payment(amount=5000)
    payment["commission_bank"] = 100
    result = match_payments(db_session, admin, admin.company_id, account.id, [payment])
    assert result["matched"] == 1
    db_session.refresh(tx)
    assert tx.jump_payment_id == "1"


def test_match_only_considers_bank_imported_transactions(client, db_session):
    """Ручные (без external_ref) операции не должны затрагиваться —
    сопоставление только для того, что реально пришло из банка."""
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, company_id=admin.company_id)
    category = make_category(db_session, company_id=admin.company_id)
    manual_tx = Transaction(
        company_id=admin.company_id,
        date_odds=date(2026, 6, 1),
        account_id=account.id,
        category_id=category.id,
        type=TxTypeEnum.expense,
        amount=Decimal("5000"),
        currency="RUB",
        amount_rub=Decimal("5000"),
        external_ref=None,
    )
    db_session.add(manual_tx)
    db_session.commit()

    result = match_payments(db_session, admin, admin.company_id, account.id, [_payment()])
    assert result["matched"] == 0
    assert result["unmatched"] == 1
