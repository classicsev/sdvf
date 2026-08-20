from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.automation_engine import apply_rules
from app.bank_import import get_or_create_counterparty
from app.models import Transaction, TxTypeEnum, User
from app.schemas import TransactionCreate


def _payment_amount_candidates(payment: dict) -> list[Decimal]:
    """Сумма, реально списанная со счёта компании за эту выплату, — Jump.Finance
    не даёт прямого поля для этого: amount — сумма заявки, amount_paid — то,
    что получил исполнитель уже за вычетом СВОЕЙ комиссии (это не банковский
    дебет), commission_bank — комиссия банка, которая может как входить в
    общий дебет счёта, так и списываться отдельной строкой в выписке. Пробуем
    оба правдоподобных варианта, а не гадаем один."""
    amount = payment.get("amount")
    if amount is None:
        return []
    candidates = [Decimal(str(amount))]
    commission_bank = payment.get("commission_bank")
    if commission_bank:
        candidates.append(Decimal(str(amount)) + Decimal(str(commission_bank)))
    return candidates


def _payment_date(payment: dict) -> Optional[date]:
    raw = payment.get("paid_at") or payment.get("created_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def match_payments(
    db: Session,
    user: User,
    company_id: str,
    account_id: str,
    payments: Iterable[dict],
    date_window_days: int = 3,
) -> dict:
    """Сопоставляет выплаты Jump.Finance с уже загруженными (обычно из
    Т-Банка) операциями по счёту — НЕ создаёт новые операции, только
    обогащает существующие: подставляет контрагента-исполнителя и, если
    получится определить, статью/проект. Источник статьи/проекта — сначала
    "контрагент по умолчанию" (см. Counterparty.default_category_id, сам
    запоминается при ручной правке — routers/transactions.py::update_transaction),
    иначе — обычные правила автоматизации компании (те же, что для
    вручную/по банку созданных операций).

    Сопоставление по сумме+дате (±date_window_days), а не по прямой ссылке —
    Jump.Finance её не даёт. Идемпотентно: уже сопоставленные (jump_payment_id
    заполнен) операции повторно не трогаются, поэтому безопасно гонять на
    каждом синке Т-Банка, а не только один раз."""
    matched = 0
    category_from_default = 0
    category_from_rule = 0
    unmatched = 0
    ambiguous = 0

    for payment in payments:
        payment_id = str(payment.get("id") or "")
        if not payment_id:
            unmatched += 1
            continue

        already = (
            db.query(Transaction)
            .filter(Transaction.company_id == company_id, Transaction.jump_payment_id == payment_id)
            .first()
        )
        if already:
            continue

        amount_candidates = _payment_amount_candidates(payment)
        pay_date = _payment_date(payment)
        if not amount_candidates or pay_date is None:
            unmatched += 1
            continue

        window_start = pay_date - timedelta(days=date_window_days)
        window_end = pay_date + timedelta(days=date_window_days)

        candidates = (
            db.query(Transaction)
            .filter(
                Transaction.company_id == company_id,
                Transaction.account_id == account_id,
                Transaction.type == TxTypeEnum.expense,
                Transaction.jump_payment_id.is_(None),
                Transaction.external_ref.isnot(None),
                Transaction.amount.in_(amount_candidates),
                Transaction.date_odds >= window_start,
                Transaction.date_odds <= window_end,
            )
            .all()
        )

        if len(candidates) != 1:
            if len(candidates) > 1:
                ambiguous += 1
            else:
                unmatched += 1
            continue

        tx = candidates[0]
        contractor = payment.get("contractor") or {}
        contractor_name = contractor.get("full_name") or contractor.get("short_name")
        if not contractor_name:
            unmatched += 1
            continue

        counterparty = get_or_create_counterparty(db, contractor_name, company_id)
        tx.counterparty_id = counterparty.id
        tx.jump_payment_id = payment_id
        purpose = payment.get("payment_purpose")
        if purpose and not tx.bank_payment_purpose:
            tx.bank_payment_purpose = purpose

        if counterparty.default_category_id:
            tx.category_id = counterparty.default_category_id
            if counterparty.default_project_id:
                tx.project_id = counterparty.default_project_id
            category_from_default += 1
        else:
            fake_payload = TransactionCreate(
                date_odds=tx.date_odds,
                account_id=tx.account_id,
                category_id=tx.category_id,
                project_id=tx.project_id,
                counterparty_id=tx.counterparty_id,
                type=tx.type,
                amount=tx.amount,
                currency=tx.currency,
                commission=tx.commission or 0,
                comment=tx.comment,
                bank_payment_purpose=tx.bank_payment_purpose,
            )
            overrides = apply_rules(db, fake_payload, company_id)
            if overrides.get("category_id"):
                tx.category_id = overrides["category_id"]
                category_from_rule += 1
            if overrides.get("project_id"):
                tx.project_id = overrides["project_id"]

        tx.updated_by = user.id
        matched += 1

    db.commit()
    return {
        "matched": matched,
        "category_set_from_default": category_from_default,
        "category_set_from_rule": category_from_rule,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
    }
