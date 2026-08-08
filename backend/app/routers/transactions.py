from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session, Query

from app.audit import log_action
from app.auth import get_current_user, require_module, require_roles, scope_project_filter
from app.automation_engine import apply_rules
from app.database import get_db
from app.fx import convert_to_rub
from app.models import Account, Category, Counterparty, Project, RoleEnum, Transaction, User
from app.schemas import TransactionCreate, TransactionOut, TransactionUpdate
from app.utils import get_or_404

router = APIRouter(prefix="/transactions", tags=["transactions"])

# Роли, которым разрешено создавать/редактировать операции (см. матрицу прав в README)
EDITORS = [RoleEnum.admin, RoleEnum.operator]


def _convert_to_rub(db: Session, currency: str, amount, on_date: date) -> Decimal:
    rub = convert_to_rub(db, currency, amount, on_date)
    if rub is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Нет курса {currency}→RUB на дату {on_date} или раньше",
        )
    return rub


def _filtered_query(
    db: Session,
    user: User,
    project: Optional[str],
    account: Optional[str],
    category: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
) -> Query:
    query = db.query(Transaction).filter(Transaction.company_id == user.company_id)

    # Row-level security: project_manager принудительно видит только свой проект,
    # даже если он передаст другой ?project= в запросе.
    forced_project = scope_project_filter(user)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)
    elif project:
        query = query.filter(Transaction.project_id == project)

    if account:
        query = query.filter(Transaction.account_id == account)
    if category:
        query = query.filter(Transaction.category_id == category)
    if date_from:
        query = query.filter(Transaction.date_odds >= date_from)
    if date_to:
        query = query.filter(Transaction.date_odds <= date_to)

    return query.order_by(Transaction.date_odds.desc())


def _get_transaction_or_404(db: Session, transaction_id: str, company_id: str) -> Transaction:
    return get_or_404(db, Transaction, transaction_id, "Операция не найдена", company_id=company_id)


def _check_can_edit(user: User, tx: Transaction) -> None:
    # operator может редактировать только созданные им операции; admin — любые
    # (см. матрицу прав в README).
    if user.role == RoleEnum.operator and tx.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator может редактировать только свои операции",
        )


@router.get("", response_model=list[TransactionOut], dependencies=[Depends(require_module("finance"))])
def list_transactions(
    project: Optional[str] = None,
    account: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _filtered_query(db, user, project, account, category, date_from, date_to).all()


@router.post(
    "",
    response_model=TransactionOut,
    dependencies=[Depends(require_roles(EDITORS)), Depends(require_module("finance"))],
)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    amount_rub = _convert_to_rub(db, payload.currency, payload.amount, payload.date_odds)

    # Правила автоматизации (см. /automation-rules) могут переопределить
    # категорию/проект операции по условиям (контрагент, комментарий, сумма).
    data = payload.model_dump()
    data.update(apply_rules(db, payload, user.company_id))

    tx = Transaction(
        **data,
        amount_rub=amount_rub,
        company_id=user.company_id,
        created_by=user.id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    log_action(db, user, action="create", entity_type="transaction", entity_id=tx.id)
    return tx


@router.patch(
    "/{transaction_id}",
    response_model=TransactionOut,
    dependencies=[Depends(require_roles(EDITORS)), Depends(require_module("finance"))],
)
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tx = _get_transaction_or_404(db, transaction_id, user.company_id)
    _check_can_edit(user, tx)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tx, field, value)

    # Пересчитываем amount_rub, только если поменялось что-то, влияющее на курс
    if {"amount", "currency", "date_odds"} & changes.keys():
        tx.amount_rub = _convert_to_rub(db, tx.currency, tx.amount, tx.date_odds)

    tx.updated_by = user.id
    db.commit()
    db.refresh(tx)
    log_action(db, user, action="update", entity_type="transaction", entity_id=tx.id, details=changes)
    return tx


@router.delete(
    "/{transaction_id}",
    dependencies=[Depends(require_roles(EDITORS)), Depends(require_module("finance"))],
)
def delete_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tx = _get_transaction_or_404(db, transaction_id, user.company_id)
    _check_can_edit(user, tx)

    db.delete(tx)
    db.commit()
    log_action(db, user, action="delete", entity_type="transaction", entity_id=transaction_id)
    return {"deleted": True}


@router.get("/export.xlsx", dependencies=[Depends(require_module("finance"))])
def export_transactions_xlsx(
    project: Optional[str] = None,
    account: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = _filtered_query(db, user, project, account, category, date_from, date_to).all()

    account_names = {a.id: a.name for a in db.query(Account).filter(Account.company_id == user.company_id).all()}
    category_names = {c.id: c.name for c in db.query(Category).filter(Category.company_id == user.company_id).all()}
    project_names = {p.id: p.name for p in db.query(Project).filter(Project.company_id == user.company_id).all()}
    counterparty_names = {
        c.id: c.name for c in db.query(Counterparty).filter(Counterparty.company_id == user.company_id).all()
    }

    wb = Workbook()
    ws = wb.active
    ws.title = "Операции"
    ws.append(
        [
            "Дата операции", "Дата ОПУ", "Тип", "Счёт", "Статья", "Проект",
            "Контрагент", "Сумма", "Валюта", "Сумма (руб.)", "Комиссия", "Комментарий",
        ]
    )
    for tx in rows:
        ws.append(
            [
                tx.date_odds.isoformat(),
                tx.date_opu.isoformat() if tx.date_opu else None,
                tx.type.value,
                account_names.get(tx.account_id, ""),
                category_names.get(tx.category_id, ""),
                project_names.get(tx.project_id, "") if tx.project_id else "",
                counterparty_names.get(tx.counterparty_id, "") if tx.counterparty_id else "",
                float(tx.amount),
                tx.currency,
                float(tx.amount_rub),
                float(tx.commission),
                tx.comment,
            ]
        )

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transactions.xlsx"},
    )
