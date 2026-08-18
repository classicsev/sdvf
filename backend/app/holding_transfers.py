import re
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Account, Category, TxTypeEnum

# Реальный номер р/с в РФ — всегда 20 цифр (см. Account.account_number).
ACCOUNT_NUMBER_RE = re.compile(r"\b\d{20}\b")


def get_or_create_internal_transfer_category(db: Session, tx_type: TxTypeEnum, company_id: str) -> Category:
    # Перевод между своими же счетами/компаниями/физлицами в одном холдинге —
    # деньги не заработаны и не потрачены, просто переложены. Как is_financing,
    # исключается из П&Л/дашборда, но остаётся в списке операций и в остатке счёта.
    name = "Перевод между своими счетами: пополнение" if tx_type == "income" else "Перевод между своими счетами: списание"
    category = db.query(Category).filter(Category.company_id == company_id, Category.name == name).first()
    if category is None:
        category = Category(
            company_id=company_id,
            name=name,
            group_name="Внутренние переводы",
            type=tx_type,
            is_internal_transfer=True,
        )
        db.add(category)
        db.flush()
    return category


def detect_internal_transfer(
    db: Session,
    holding_company_ids: List[str],
    own_account_id: str,
    comment: Optional[str],
) -> bool:
    """Ищет в описании операции номер счёта (20 цифр), принадлежащий другому
    счёту в этом же холдинге (счёт может быть и в той же компании — перевод
    между своими же р/с, и в другой компании/у физлица, добавленного в тот же
    аккаунт) — тогда это перевод между своими, а не реальный приход/расход.

    Работает только там, где банк сам печатает номер счёта получателя/
    отправителя в описании операции (не все банки его показывают — см.
    statement_parsers/*). Остальное помечается вручную выбором категории
    "Перевод между своими счетами" в списке операций.
    """
    if not comment or not holding_company_ids:
        return False
    candidates = set(ACCOUNT_NUMBER_RE.findall(comment))
    if not candidates:
        return False
    match = (
        db.query(Account.id)
        .filter(
            Account.account_number.in_(candidates),
            Account.company_id.in_(holding_company_ids),
            Account.id != own_account_id,
        )
        .first()
    )
    return match is not None
