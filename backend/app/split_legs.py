from sqlalchemy import case, select, union_all
from sqlalchemy.orm import Session
from sqlalchemy.sql import Subquery

from app.models import Transaction, TransactionCategorySplit, TransactionProjectSplit


def category_amount_legs(db: Session) -> Subquery:
    """Один ряд на (transaction_id, category_id, amount_rub) — для операций
    БЕЗ разбивки по статьям ряд один и amount_rub — вся сумма операции; для
    разбитых — по ряду на каждую долю, amount_rub — доля, не вся сумма.

    Не несёт остальных колонок Transaction (дата, компания, подтверждения,
    проект и т.п.) — за ними join'ить обратно на Transaction по
    transaction_id, чтобы не дублировать/рассинхронизировать passthrough-
    данные между веткой union'а."""
    split_transaction_ids = select(TransactionCategorySplit.transaction_id).distinct().subquery()
    unsplit = select(
        Transaction.id.label("transaction_id"),
        Transaction.category_id.label("category_id"),
        Transaction.amount_rub.label("amount_rub"),
    ).where(
        Transaction.category_id.isnot(None),
        Transaction.id.not_in(select(split_transaction_ids.c.transaction_id)),
    )
    split = select(
        TransactionCategorySplit.transaction_id.label("transaction_id"),
        TransactionCategorySplit.category_id.label("category_id"),
        TransactionCategorySplit.amount_rub.label("amount_rub"),
    )
    return union_all(unsplit, split).subquery("category_legs")


def project_amount_legs(db: Session) -> Subquery:
    """Симметрично category_amount_legs, по проектным долям — ряд существует
    только для операций, у которых реально ЕСТЬ проект (прямой или через
    разбивку); операции без проекта тут не появляются вовсе."""
    split_transaction_ids = select(TransactionProjectSplit.transaction_id).distinct().subquery()
    unsplit = select(
        Transaction.id.label("transaction_id"),
        Transaction.project_id.label("project_id"),
        Transaction.amount_rub.label("amount_rub"),
    ).where(
        Transaction.project_id.isnot(None),
        Transaction.id.not_in(select(split_transaction_ids.c.transaction_id)),
    )
    split = select(
        TransactionProjectSplit.transaction_id.label("transaction_id"),
        TransactionProjectSplit.project_id.label("project_id"),
        TransactionProjectSplit.amount_rub.label("amount_rub"),
    )
    return union_all(unsplit, split).subquery("project_legs")


def project_category_amount_legs(db: Session) -> Subquery:
    """Один ряд на пересечение (доля проекта × доля статьи) одной операции —
    нужна ТОЛЬКО там, где надо разбить расход по статьям ВНУТРИ конкретного
    проекта (project_detail), а операция при этом может быть разбита по
    ОБОИМ измерениям одновременно, независимо друг от друга. amount_rub —
    пропорциональная доля: project_leg.amount_rub * category_leg.amount_rub
    / transaction.amount_rub (0, если amount_rub операции — 0).

    Для операции, разбитой только по ОДНОМУ измерению (типичный случай —
    пример пользователя "3000 ₽ на 3 проекта, статья одна"), формула
    сводится ровно к доле того единственного разбитого измерения — не
    приближение, а точная арифметика в этом частом случае. Приближение
    (пропорциональное распределение, а не точная 2D-раскладка) действует
    только когда ОБА измерения разбиты на одной и той же операции —
    пользователь эту связь явно не указывает (выбирает доли по проектам и
    по статьям независимо), так что пропорциональное распределение —
    единственный осмысленный способ не потерять и не задвоить сумму."""
    project_legs = project_amount_legs(db)
    category_legs = category_amount_legs(db)
    return (
        select(
            project_legs.c.transaction_id.label("transaction_id"),
            project_legs.c.project_id.label("project_id"),
            category_legs.c.category_id.label("category_id"),
            case(
                (Transaction.amount_rub == 0, 0),
                else_=project_legs.c.amount_rub * category_legs.c.amount_rub / Transaction.amount_rub,
            ).label("amount_rub"),
        )
        .select_from(project_legs)
        .join(category_legs, category_legs.c.transaction_id == project_legs.c.transaction_id)
        .join(Transaction, Transaction.id == project_legs.c.transaction_id)
        .subquery("project_category_legs")
    )
