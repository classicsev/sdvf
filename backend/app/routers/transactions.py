from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session, Query

from app.audit import log_action
from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids,
    resolve_write_company_id,
    scope_project_filter,
)
from app.automation_engine import apply_rules
from app.database import get_db
from app.fx import convert_to_rub
from app.holding_transfers import get_or_create_internal_transfer_category
from app.models import Account, Category, Counterparty, Order, Project, RoleEnum, Transaction, TxTypeEnum, User
from app.reference_scope import get_visible_or_404
from app.schemas import (
    CloseMonthIn,
    ReclassCreate,
    ReclassOut,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
    TransactionBatchDelete,
    TransferCreate,
    TransferOut,
)
from app.utils import get_or_404_accessible

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
    company_id: Optional[str],
    project: Optional[str],
    account: Optional[str],
    category: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    project_group_id: Optional[str] = None,
    confirmed: Optional[str] = None,
) -> Query:
    # Без ?company_id= — сразу по всем компаниям пользователя (сводно, без
    # переключения контекста); с ?company_id= — только по одной.
    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(Transaction).filter(Transaction.company_id.in_(company_ids))

    # Row-level security: project_manager принудительно видит только свой проект,
    # даже если он передаст другой ?project= в запросе.
    forced_project = scope_project_filter(user)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)
    elif project:
        query = query.filter(Transaction.project_id == project)
    elif project_group_id:
        query = query.filter(
            Transaction.project_id.in_(db.query(Project.id).filter(Project.group_id == project_group_id))
        )

    if account:
        query = query.filter(Transaction.account_id == account)
    if category:
        query = query.filter(Transaction.category_id == category)
    if date_from:
        query = query.filter(Transaction.date_odds >= date_from)
    if date_to:
        query = query.filter(Transaction.date_odds <= date_to)
    if confirmed == "unconfirmed":
        query = query.filter(
            (Transaction.payment_confirmed.is_(False)) | (Transaction.accrual_confirmed.is_(False))
        )
    elif confirmed == "confirmed":
        query = query.filter(
            Transaction.payment_confirmed.is_(True), Transaction.accrual_confirmed.is_(True)
        )

    # Тай-брейкер обязателен: при пагинации (.limit().offset()) Postgres не
    # гарантирует стабильный порядок строк с одинаковой date_odds между
    # отдельными запросами — без второго ключа сортировки операции одной
    # датой могут задваиваться/пропадать между страницами списка.
    return query.order_by(Transaction.date_odds.desc(), Transaction.created_at.desc())


def _get_transaction_or_404(db: Session, user: User, transaction_id: str) -> Transaction:
    return get_or_404_accessible(
        db, Transaction, transaction_id, get_accessible_company_ids(db, user), "Операция не найдена"
    )


def _check_can_edit(user: User, tx: Transaction, role: RoleEnum) -> None:
    # operator может редактировать только созданные им операции; admin — любые
    # (см. матрицу прав в README). Роль проверяется для компании самой
    # операции (tx.company_id), не "первой" компании пользователя — см.
    # check_company_role в вызывающем коде.
    if role == RoleEnum.operator and tx.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator может редактировать только свои операции",
        )


@router.get("", response_model=list[TransactionOut], dependencies=[Depends(require_module("finance"))])
def list_transactions(
    company_id: Optional[str] = None,
    project: Optional[str] = None,
    account: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    project_group_id: Optional[str] = None,
    confirmed: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    all_records: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Список операций с пагинацией.
    - limit: размер страницы (по умолчанию 50, максимум 1000)
    - skip: количество пропускаемых записей (по умолчанию 0)
    - all_records: вернуть все записи без пагинации (игнорирует limit и skip)
    - project_group_id: все операции по проектам данной группы (игнорируется, если задан project)
    - confirmed: "confirmed" | "unconfirmed" — по статусу подтверждения оплаты/начисления
    """
    args = (db, user, company_id, project, account, category, date_from, date_to, project_group_id, confirmed)
    if all_records:
        return _filtered_query(*args).all()

    # Валидация limit
    if limit < 1 or limit > 1000:
        limit = 50
    if skip < 0:
        skip = 0

    return _filtered_query(*args).limit(limit).offset(skip).all()


@router.get("/count", response_model=int, dependencies=[Depends(require_module("finance"))])
def count_transactions(
    company_id: Optional[str] = None,
    project: Optional[str] = None,
    account: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    project_group_id: Optional[str] = None,
    confirmed: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Общее количество операций, подходящих под фильтры."""
    return _filtered_query(
        db, user, company_id, project, account, category, date_from, date_to, project_group_id, confirmed
    ).count()


@router.post(
    "",
    response_model=TransactionOut,
    dependencies=[Depends(require_module("finance"))],
)
def create_transaction(
    payload: TransactionCreate,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, EDITORS)

    # Счёт/статья/проект/контрагент обязаны принадлежать той же компании, что и
    # сама операция — иначе можно было бы создать операцию в одной компании,
    # ссылаясь на справочники другой (утечка между компаниями).
    get_or_404_accessible(db, Account, payload.account_id, [target], "Счёт не найден")
    # Статья/проект — не строгое совпадение company_id, а "видна ли компании
    # target" (своя, глобальная или явно расшаренная — см. reference_scope.py).
    get_visible_or_404(db, Category, payload.category_id, [target], "Статья не найдена")
    if payload.project_id:
        get_visible_or_404(db, Project, payload.project_id, [target], "Проект не найден")
    if payload.counterparty_id:
        get_or_404_accessible(db, Counterparty, payload.counterparty_id, [target], "Контрагент не найден")
    if payload.order_id:
        get_or_404_accessible(db, Order, payload.order_id, [target], "Заказ не найден")

    amount_rub = _convert_to_rub(db, payload.currency, payload.amount, payload.date_odds)

    # Правила автоматизации (см. /automation-rules) могут переопределить
    # категорию/проект операции по условиям (контрагент, комментарий, сумма).
    data = payload.model_dump()
    data.update(apply_rules(db, payload, target))

    tx = Transaction(
        **data,
        amount_rub=amount_rub,
        company_id=target,
        created_by=user.id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    log_action(db, user, action="create", entity_type="transaction", entity_id=tx.id, company_id=target)
    return tx


@router.post(
    "/transfer",
    response_model=TransferOut,
    dependencies=[Depends(require_module("finance"))],
)
def create_transfer(
    payload: TransferCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Перевод между своими счетами (в т.ч. между двумя компаниями одного
    холдинга) — деньги никуда не заработались и не потратились, просто
    переложены из одного кармана в другой. Создаёт ДВЕ строки Transaction
    (списание + зачисление) с уже существующими категориями
    is_internal_transfer=True (см. app/holding_transfers.py — эти категории
    исключены из П&Л/дашборда, но остаются в списке операций и в остатке
    счёта), связанные друг с другом через transfer_pair_id."""
    if payload.from_account_id == payload.to_account_id:
        raise HTTPException(status_code=422, detail="Счёт списания и счёт зачисления должны различаться")

    accessible = get_accessible_company_ids(db, user)
    from_account = get_or_404_accessible(db, Account, payload.from_account_id, accessible, "Счёт списания не найден")
    to_account = get_or_404_accessible(db, Account, payload.to_account_id, accessible, "Счёт зачисления не найден")
    check_company_role(db, user, from_account.company_id, EDITORS)
    check_company_role(db, user, to_account.company_id, EDITORS)

    if from_account.currency != to_account.currency:
        raise HTTPException(
            status_code=422,
            detail=f"Счета в разных валютах ({from_account.currency} и {to_account.currency}) — перевод между ними пока не поддержан",
        )

    amount_rub = _convert_to_rub(db, from_account.currency, payload.amount, payload.date_odds)

    expense_category = get_or_create_internal_transfer_category(db, TxTypeEnum.expense, from_account.company_id)
    income_category = get_or_create_internal_transfer_category(db, TxTypeEnum.income, to_account.company_id)
    db.commit()

    expense_tx = Transaction(
        company_id=from_account.company_id,
        date_odds=payload.date_odds,
        date_opu=payload.date_opu,
        account_id=from_account.id,
        category_id=expense_category.id,
        type=TxTypeEnum.expense,
        amount=payload.amount,
        currency=from_account.currency,
        amount_rub=amount_rub,
        commission=payload.commission,
        comment=payload.comment,
        payment_confirmed=payload.payment_confirmed,
        created_by=user.id,
    )
    income_tx = Transaction(
        company_id=to_account.company_id,
        date_odds=payload.date_odds,
        date_opu=payload.date_opu,
        account_id=to_account.id,
        category_id=income_category.id,
        type=TxTypeEnum.income,
        amount=payload.amount,
        currency=to_account.currency,
        amount_rub=amount_rub,
        comment=payload.comment,
        payment_confirmed=payload.payment_confirmed,
        created_by=user.id,
    )
    db.add(expense_tx)
    db.add(income_tx)
    db.flush()
    expense_tx.transfer_pair_id = income_tx.id
    income_tx.transfer_pair_id = expense_tx.id
    db.commit()
    db.refresh(expense_tx)
    db.refresh(income_tx)
    log_action(db, user, action="create", entity_type="transaction", entity_id=expense_tx.id, company_id=from_account.company_id)
    log_action(db, user, action="create", entity_type="transaction", entity_id=income_tx.id, company_id=to_account.company_id)
    return TransferOut(expense=expense_tx, income=income_tx)


@router.post(
    "/reclass",
    response_model=ReclassOut,
    dependencies=[Depends(require_module("finance"))],
)
def create_reclass(
    payload: ReclassCreate,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Операция "Начисление" — перенос уже учтённой суммы с одной статьи на
    другую БЕЗ движения денег (напр. расход по ошибке завели под одну
    статью, нужно перенести на другую). Создаёт ДВЕ строки Transaction
    ОДНОГО типа (income/income или expense/expense) с ПРОТИВОПОЛОЖНЫМ знаком
    amount — одна гасит исходную статью, другая добавляет в целевую, в
    сумме ноль (общий П&Л не меняется, меняется только разбивка по статьям).
    Обе ноги исключены из остатка счёта через reclass_pair_id (см.
    _account_balance/reconcile_opening_balance) — account_id указывается
    только для отображения в списке операций."""
    target = resolve_write_company_id(db, user, company_id, EDITORS)

    if payload.from_category_id == payload.to_category_id:
        raise HTTPException(status_code=422, detail="Статья списания и статья зачисления должны различаться")

    get_or_404_accessible(db, Account, payload.account_id, [target], "Счёт не найден")
    from_category = get_visible_or_404(db, Category, payload.from_category_id, [target], "Статья списания не найдена")
    to_category = get_visible_or_404(db, Category, payload.to_category_id, [target], "Статья зачисления не найдена")

    if from_category.type != to_category.type:
        raise HTTPException(
            status_code=422,
            detail="Нельзя переносить сумму между статьями разного типа (доход/расход)",
        )

    amount_rub = _convert_to_rub(db, payload.currency, payload.amount, payload.date_odds)

    from_leg = Transaction(
        company_id=target,
        date_odds=payload.date_odds,
        date_opu=payload.date_opu,
        account_id=payload.account_id,
        category_id=from_category.id,
        type=from_category.type,
        amount=-payload.amount,
        currency=payload.currency,
        amount_rub=-amount_rub,
        comment=payload.comment,
        created_by=user.id,
    )
    to_leg = Transaction(
        company_id=target,
        date_odds=payload.date_odds,
        date_opu=payload.date_opu,
        account_id=payload.account_id,
        category_id=to_category.id,
        type=to_category.type,
        amount=payload.amount,
        currency=payload.currency,
        amount_rub=amount_rub,
        comment=payload.comment,
        created_by=user.id,
    )
    db.add(from_leg)
    db.add(to_leg)
    db.flush()
    from_leg.reclass_pair_id = to_leg.id
    to_leg.reclass_pair_id = from_leg.id
    db.commit()
    db.refresh(from_leg)
    db.refresh(to_leg)
    log_action(db, user, action="create", entity_type="transaction", entity_id=from_leg.id, company_id=target)
    log_action(db, user, action="create", entity_type="transaction", entity_id=to_leg.id, company_id=target)
    return ReclassOut(from_leg=from_leg, to_leg=to_leg)


@router.patch(
    "/{transaction_id}",
    response_model=TransactionOut,
    dependencies=[Depends(require_module("finance"))],
)
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tx = _get_transaction_or_404(db, user, transaction_id)
    # Роль проверяется для компании самой операции — пользователь может быть
    # admin в одной своей компании и viewer в другой (см. план "Мульти-компании").
    role = check_company_role(db, user, tx.company_id, EDITORS)
    _check_can_edit(user, tx, role)

    changes = payload.model_dump(exclude_unset=True)

    # При смене счёта/статьи/проекта/контрагента — та же защита от межкомпанийной
    # ссылки, что и при создании (см. create_transaction).
    if changes.get("account_id"):
        get_or_404_accessible(db, Account, changes["account_id"], [tx.company_id], "Счёт не найден")
    if changes.get("category_id"):
        get_visible_or_404(db, Category, changes["category_id"], [tx.company_id], "Статья не найдена")
    if changes.get("project_id"):
        get_visible_or_404(db, Project, changes["project_id"], [tx.company_id], "Проект не найден")
    if changes.get("counterparty_id"):
        get_or_404_accessible(db, Counterparty, changes["counterparty_id"], [tx.company_id], "Контрагент не найден")
    if changes.get("order_id"):
        get_or_404_accessible(db, Order, changes["order_id"], [tx.company_id], "Заказ не найден")

    for field, value in changes.items():
        setattr(tx, field, value)

    # Пересчитываем amount_rub, только если поменялось что-то, влияющее на курс
    if {"amount", "currency", "date_odds"} & changes.keys():
        tx.amount_rub = _convert_to_rub(db, tx.currency, tx.amount, tx.date_odds)

    # Операция, сопоставленная с выплатой Jump.Finance (jump_payment_id
    # заполнен — см. jump_matching.py) — при ручной правке статьи/проекта
    # запоминаем выбор на самом контрагенте (Counterparty.default_category_id/
    # default_project_id), чтобы при следующем сопоставлении с тем же
    # исполнителем статья/проект подставились сами, без правил автоматизации.
    if tx.jump_payment_id and tx.counterparty_id and ({"category_id", "project_id"} & changes.keys()):
        counterparty = db.get(Counterparty, tx.counterparty_id)
        if counterparty:
            if "category_id" in changes:
                counterparty.default_category_id = tx.category_id
            if "project_id" in changes:
                counterparty.default_project_id = tx.project_id

    tx.updated_by = user.id
    db.commit()
    db.refresh(tx)
    log_action(db, user, action="update", entity_type="transaction", entity_id=tx.id, details=changes, company_id=tx.company_id)
    return tx


@router.post("/close-month", dependencies=[Depends(require_module("finance"))])
def close_month(
    payload: CloseMonthIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Массово проставляет дату начисления (date_opu) = 1-е число месяца —
    только там, где она ещё не задана вручную (не перезаписывает). Доступно
    только admin — полу-необратимое действие уровня "закрытие периода"."""
    check_company_role(db, user, payload.company_id, [RoleEnum.admin])
    month_start = payload.month.replace(day=1)
    next_month = date(month_start.year + (month_start.month == 12), (month_start.month % 12) + 1, 1)
    updated = (
        db.query(Transaction)
        .filter(
            Transaction.company_id == payload.company_id,
            Transaction.date_odds >= month_start,
            Transaction.date_odds < next_month,
            Transaction.date_opu.is_(None),
        )
        .update({"date_opu": month_start}, synchronize_session=False)
    )
    db.commit()
    log_action(
        db,
        user,
        action="close_month",
        entity_type="transaction",
        details={"month": month_start.isoformat(), "updated": updated},
        company_id=payload.company_id,
    )
    return {"updated": updated, "month": month_start.isoformat()}


@router.delete(
    "/{transaction_id}",
    dependencies=[Depends(require_module("finance"))],
)
def delete_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tx = _get_transaction_or_404(db, user, transaction_id)
    role = check_company_role(db, user, tx.company_id, EDITORS)
    _check_can_edit(user, tx, role)
    tx_company_id = tx.company_id

    # Часть "Перемещения" (create_transfer) или "Начисления" (create_reclass)
    # — удаляем сразу обе стороны, иначе останется висячая нога без пары,
    # искажающая остаток счёта или разбивку по статьям.
    pair_id = tx.transfer_pair_id or tx.reclass_pair_id
    pair = None
    if pair_id:
        pair = db.get(Transaction, pair_id)
        if pair:
            check_company_role(db, user, pair.company_id, EDITORS)
            _check_can_edit(user, pair, role)

    db.delete(tx)
    if pair:
        db.delete(pair)
    db.commit()
    log_action(db, user, action="delete", entity_type="transaction", entity_id=transaction_id, company_id=tx_company_id)
    if pair:
        log_action(db, user, action="delete", entity_type="transaction", entity_id=pair.id, company_id=pair.company_id)
    return {"deleted": True, "paired_deleted": pair is not None}


@router.delete(
    "/batch",
    dependencies=[Depends(require_module("finance"))],
)
def batch_delete_transactions(
    payload: TransactionBatchDelete,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Пакетное удаление нескольких операций.
    Проверяет права для каждой операции отдельно.
    """
    if not payload.transaction_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Массив transaction_ids не может быть пустым"
        )

    # Берём все операции, доступные пользователю
    accessible_company_ids = get_accessible_company_ids(db, user)
    transactions = db.query(Transaction).filter(
        Transaction.id.in_(payload.transaction_ids),
        Transaction.company_id.in_(accessible_company_ids)
    ).all()

    if len(transactions) != len(payload.transaction_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Одна или несколько операций не найдены или недоступны"
        )

    deleted_count = 0
    failed_ids = []

    for tx in transactions:
        try:
            # Проверяем права на редактирование каждой операции
            role = check_company_role(db, user, tx.company_id, EDITORS)
            _check_can_edit(user, tx, role)

            # Удаляем и логируем
            tx_id = tx.id
            tx_company_id = tx.company_id
            db.delete(tx)
            log_action(db, user, action="delete", entity_type="transaction", entity_id=tx_id, company_id=tx_company_id)
            deleted_count += 1
        except HTTPException:
            # Если нет прав на редактирование конкретной операции — добавляем в failed
            failed_ids.append(tx.id)

    db.commit()

    return {
        "deleted": deleted_count,
        "total_requested": len(payload.transaction_ids),
        "failed_ids": failed_ids,
        "message": f"Удалено {deleted_count} из {len(payload.transaction_ids)} операций"
    }


@router.post(
    "/batch-delete-by-filter",
    dependencies=[Depends(require_module("finance"))],
)
def batch_delete_transactions_by_filter(
    company_id: Optional[str] = None,
    project: Optional[str] = None,
    account: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    project_group_id: Optional[str] = None,
    confirmed: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Пакетное удаление всех операций, соответствующих текущим фильтрам.
    Проверяет права для каждой операции отдельно.
    """
    transactions = _filtered_query(
        db, user, company_id, project, account, category, date_from, date_to, project_group_id, confirmed
    ).all()

    deleted_count = 0
    failed_ids = []

    for tx in transactions:
        try:
            role = check_company_role(db, user, tx.company_id, EDITORS)
            _check_can_edit(user, tx, role)

            tx_id = tx.id
            tx_company_id = tx.company_id
            db.delete(tx)
            log_action(db, user, action="delete", entity_type="transaction", entity_id=tx_id, company_id=tx_company_id)
            deleted_count += 1
        except HTTPException:
            failed_ids.append(tx.id)

    db.commit()

    return {
        "deleted": deleted_count,
        "total_requested": len(transactions),
        "failed_ids": failed_ids,
        "message": f"Удалено {deleted_count} из {len(transactions)} операций"
    }


@router.get("/export.xlsx", dependencies=[Depends(require_module("finance"))])
def export_transactions_xlsx(
    company_id: Optional[str] = None,
    project: Optional[str] = None,
    account: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    project_group_id: Optional[str] = None,
    confirmed: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = _filtered_query(
        db, user, company_id, project, account, category, date_from, date_to, project_group_id, confirmed
    ).all()
    company_ids = resolve_company_ids(db, user, company_id)

    account_names = {a.id: a.name for a in db.query(Account).filter(Account.company_id.in_(company_ids)).all()}
    category_names = {c.id: c.name for c in db.query(Category).filter(Category.company_id.in_(company_ids)).all()}
    project_names = {p.id: p.name for p in db.query(Project).filter(Project.company_id.in_(company_ids)).all()}
    counterparty_names = {
        c.id: c.name for c in db.query(Counterparty).filter(Counterparty.company_id.in_(company_ids)).all()
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
