from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import Account, Transaction, TxTypeEnum


def reconcile_opening_balance(
    db: Session, account: Account, current_balance: Decimal, as_of: Optional[date] = None
) -> Account:
    """Решает opening_balance = current_balance − поток по уже введённым операциям
    на as_of (по умолчанию сегодня), чтобы расчётный остаток в Учёте совпал с
    current_balance день-в-день (см. routers/reference.py::set_account_current_balance
    и routers/statements.py::import_statement — оба используют эту же формулу).

    Не коммитит — вызывающий код сам решает, когда коммитить (в statements.py это
    та же транзакция БД, что и только что импортированные операции, — чтобы
    остаток применялся атомарно вместе с импортом, а не отдельным шагом, который
    можно забыть/пропустить).
    """
    resolved_as_of = as_of or date.today()
    # Флаш обязателен: сессия работает с autoflush=False (см. database.py), а
    # только что добавленные через db.add() операции (например, из только что
    # выполненного импорта выписки) должны попасть в этот SUM — иначе остаток
    # посчитается без них и разъедется с реальностью.
    db.flush()
    flow = (
        db.query(
            func.sum(
                case(
                    (Transaction.type == TxTypeEnum.income, Transaction.amount),
                    else_=-Transaction.amount,
                )
            )
        )
        .filter(
            Transaction.account_id == account.id,
            Transaction.date_odds <= resolved_as_of,
            Transaction.payment_confirmed.is_(True),
            Transaction.reclass_pair_id.is_(None),
        )
        .scalar()
    ) or Decimal("0")

    account.opening_balance = current_balance - flow
    return account
