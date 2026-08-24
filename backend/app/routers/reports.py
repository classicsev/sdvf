from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session
from sqlalchemy.orm import Query as SAQuery

from app.auth import get_current_user, require_module, require_roles, resolve_company_ids, scope_project_filter
from app.database import get_db
from app.fx import convert_to_rub
from app.models import (
    Account,
    Category,
    Company,
    Counterparty,
    PayrollAccrual,
    PayrollPayment,
    Project,
    ProjectBudgetLine,
    RoleEnum,
    Transaction,
    TxTypeEnum,
    User,
)

router = APIRouter(prefix="/reports", tags=["reports"])

# ВАЖНО (см. README): отчёты — это SQL-запросы/представления поверх transactions
# и payroll_*, а не отдельные хранимые таблицы. Один источник правды = transactions.

# По матрице прав в README у payroll_operator нет доступа к дашборду/отчётам —
# у остальных ролей есть (project_manager дополнительно ограничен RLS по проекту).
REPORT_VIEWERS = [RoleEnum.admin, RoleEnum.operator, RoleEnum.project_manager, RoleEnum.viewer]
FINANCE_MODULE = Depends(require_module("finance"))


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _current_month_bounds() -> tuple[date, date]:
    today = date.today()
    return today.replace(day=1), _month_end(today.year, today.month)


def _parse_period(period: str) -> tuple[date, date]:
    try:
        year_str, month_str = period.split("-")
        year, month = int(year_str), int(month_str)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period должен быть в формате YYYY-MM",
        )
    return date(year, month, 1), _month_end(year, month)


def _quarter_of(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    start_month = (quarter - 1) * 3 + 1
    return date(year, start_month, 1), _month_end(year, start_month + 2)


DASHBOARD_RANGES = {"today", "week", "month", "quarter", "year"}


def _resolve_dashboard_range(
    range_key: str, date_from: Optional[date], date_to: Optional[date]
) -> tuple[date, date]:
    """Возвращает (period_from, period_to) для дашборда. date_from+date_to —
    свой период (range игнорируется), иначе — стандартный пресет от сегодня."""
    if date_from and date_to:
        return date_from, date_to

    today = date.today()
    if range_key == "today":
        return today, today
    if range_key == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if range_key == "quarter":
        return _quarter_bounds(today.year, _quarter_of(today))
    if range_key == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    return _current_month_bounds()


def _previous_dashboard_range(range_key: str, period_from: date, period_to: date) -> tuple[date, date]:
    """Период для сравнения "к прошлому периоду" — календарно осмысленный для
    именованных диапазонов (прошлый месяц/квартал/год целиком, не "N дней
    назад"), для остальных — тот же по длине период непосредственно перед."""
    if range_key == "month" and period_from.day == 1 and period_to == _month_end(period_from.year, period_from.month):
        prev_month = period_from.month - 1 or 12
        prev_year = period_from.year - 1 if period_from.month == 1 else period_from.year
        return date(prev_year, prev_month, 1), _month_end(prev_year, prev_month)
    if range_key == "quarter":
        q = _quarter_of(period_from)
        prev_q, prev_year = (q - 1, period_from.year) if q > 1 else (4, period_from.year - 1)
        return _quarter_bounds(prev_year, prev_q)
    if range_key == "year" and period_from.month == 1 and period_from.day == 1:
        return date(period_from.year - 1, 1, 1), date(period_from.year - 1, 12, 31)
    length = (period_to - period_from).days + 1
    prev_to = period_from - timedelta(days=1)
    return prev_to - timedelta(days=length - 1), prev_to


def _account_balance(db: Session, account: Account, as_of: date) -> Decimal:
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
            Transaction.date_odds <= as_of,
            Transaction.payment_confirmed.is_(True),
            Transaction.reclass_pair_id.is_(None),
        )
        .scalar()
    )
    return Decimal(str(account.opening_balance)) + (flow or Decimal("0"))


def _income_expense_for_range(
    db: Session,
    company_ids: list[str],
    period_from: date,
    period_to: date,
    forced_project: Optional[str],
) -> tuple[Decimal, Decimal, dict, dict]:
    # is_financing (кредитные линии/займы и их погашение) и is_internal_transfer
    # (переводы между своими же счетами/компаниями/физлицами в одном холдинге,
    # см. app/holding_transfers.py) — не доход и не расход бизнеса, поэтому не
    # входят в "Приход/Расход" ни по одной компании, ни сводно по всем сразу
    # (свой перевод — не выручка ни там, ни там); сами операции остаются в
    # списке транзакций и в остатке счёта, просто не искажают эти сводные цифры.
    query = (
        db.query(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.company_id.in_(company_ids),
            Transaction.date_odds >= period_from,
            Transaction.date_odds <= period_to,
            Category.is_financing.is_(False),
            Category.is_internal_transfer.is_(False),
            Transaction.accrual_confirmed.is_(True),
        )
    )
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)

    income = (
        query.filter(Transaction.type == TxTypeEnum.income)
        .with_entities(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .scalar()
    )
    expense = (
        query.filter(Transaction.type == TxTypeEnum.expense)
        .with_entities(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .scalar()
    )
    income_by_company = dict(
        query.filter(Transaction.type == TxTypeEnum.income)
        .with_entities(Transaction.company_id, func.coalesce(func.sum(Transaction.amount_rub), 0))
        .group_by(Transaction.company_id)
        .all()
    )
    expense_by_company = dict(
        query.filter(Transaction.type == TxTypeEnum.expense)
        .with_entities(Transaction.company_id, func.coalesce(func.sum(Transaction.amount_rub), 0))
        .group_by(Transaction.company_id)
        .all()
    )
    return Decimal(str(income)), Decimal(str(expense)), income_by_company, expense_by_company


@router.get("/account-balances", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def account_balances(
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Лёгкий эндпоинт только для остатков по счетам — используется вкладкой
    "Балансы" на экране Операций, где не нужны доход/расход за период,
    которые dashboard-summary всё равно считает попутно (дважды: текущий и
    предыдущий период)."""
    today = date.today()
    company_ids = resolve_company_ids(db, user, company_id)
    accounts = db.query(Account).filter(Account.company_id.in_(company_ids), Account.is_active.is_(True)).all()
    rows = []
    for account in accounts:
        balance = _account_balance(db, account, today)
        balance_rub = convert_to_rub(db, account.currency, balance, today)
        rows.append(
            {
                "id": account.id,
                "name": account.name,
                "currency": account.currency,
                "balance": float(balance),
                "balance_rub": float(balance_rub) if balance_rub is not None else None,
            }
        )
    return {"accounts": rows}


@router.get("/dashboard-summary", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def dashboard_summary(
    range_: str = Query(default="month", alias="range"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = date.today()
    is_custom = bool(date_from and date_to)
    # "custom" не входит в DASHBOARD_RANGES (это именованные пресеты) — свой
    # период форсируем отдельно, иначе он может случайно совпасть по границам
    # с "месяц"/"квартал" и получить неверную (календарную) логику сравнения.
    range_key = "custom" if is_custom else (range_ if range_ in DASHBOARD_RANGES else "month")
    period_from, period_to = _resolve_dashboard_range(range_key, date_from, date_to)
    prev_from, prev_to = _previous_dashboard_range(range_key, period_from, period_to)

    # Без ?company_id= — сводно по всем компаниям пользователя (см. план
    # "Мульти-компании"): total_balance_rub и period_*_rub суммируют все
    # компании сразу, а by_company даёт разбивку по каждой без похода в фильтры.
    company_ids = resolve_company_ids(db, user, company_id)
    companies_by_id = {c.id: c.name for c in db.query(Company).filter(Company.id.in_(company_ids)).all()}

    accounts = (
        db.query(Account).filter(Account.company_id.in_(company_ids), Account.is_active.is_(True)).all()
    )
    account_rows = []
    total_balance_rub = Decimal("0")
    balance_by_company: dict[str, Decimal] = {cid: Decimal("0") for cid in company_ids}
    # Разбивка по валютам рядом с общим RUB-итогом — держит натуральный остаток
    # видимым (важно для держателей счетов не в RUB, например CNY), не подменяя
    # собой сводную рублёвую цифру, на которую завязаны остальные отчёты.
    balance_by_currency: dict[str, Decimal] = {}
    # None, пока ни один счёт этой валюты не удалось сконвертировать (нет курса
    # на дату) — отличаем от честного нулевого остатка, чтобы фронт показал
    # "нет курса", а не вводящий в заблуждение "0,00 ₽".
    balance_rub_by_currency: dict[str, Optional[Decimal]] = {}
    for account in accounts:
        balance = _account_balance(db, account, today)
        balance_rub = convert_to_rub(db, account.currency, balance, today)
        if balance_rub is not None:
            total_balance_rub += balance_rub
            balance_by_company[account.company_id] = balance_by_company.get(account.company_id, Decimal("0")) + balance_rub
            balance_rub_by_currency[account.currency] = (
                balance_rub_by_currency.get(account.currency) or Decimal("0")
            ) + balance_rub
        else:
            balance_rub_by_currency.setdefault(account.currency, None)
        balance_by_currency[account.currency] = balance_by_currency.get(account.currency, Decimal("0")) + balance
        account_rows.append(
            {
                "id": account.id,
                "company_id": account.company_id,
                "name": account.name,
                "currency": account.currency,
                "balance": float(balance),
                "balance_rub": float(balance_rub) if balance_rub is not None else None,
            }
        )

    by_currency = [
        {
            "currency": currency,
            "total_balance": float(amount),
            "total_balance_rub": (
                float(balance_rub_by_currency[currency]) if balance_rub_by_currency.get(currency) is not None else None
            ),
        }
        for currency, amount in sorted(balance_by_currency.items())
    ]

    forced_project = scope_project_filter(user)
    period_income, period_expense, income_by_company, expense_by_company = _income_expense_for_range(
        db, company_ids, period_from, period_to, forced_project
    )
    prev_income, prev_expense, _prev_income_by_company, _prev_expense_by_company = _income_expense_for_range(
        db, company_ids, prev_from, prev_to, forced_project
    )

    by_company = [
        {
            "company_id": cid,
            "company_name": companies_by_id.get(cid, ""),
            "total_balance_rub": float(balance_by_company.get(cid, Decimal("0"))),
            "period_income_rub": float(income_by_company.get(cid, 0)),
            "period_expense_rub": float(expense_by_company.get(cid, 0)),
        }
        for cid in company_ids
    ]

    net_flow = period_income - period_expense
    prev_net_flow = prev_income - prev_expense

    return {
        "accounts": account_rows,
        "total_balance_rub": float(total_balance_rub),
        "range": range_key,
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "period_income_rub": float(period_income),
        "period_expense_rub": float(period_expense),
        "net_flow_rub": float(net_flow),
        "prev_period_from": prev_from.isoformat(),
        "prev_period_to": prev_to.isoformat(),
        "prev_period_income_rub": float(prev_income),
        "prev_period_expense_rub": float(prev_expense),
        "prev_net_flow_rub": float(prev_net_flow),
        "by_company": by_company,
        "by_currency": by_currency,
    }


@router.get("/cashflow-forecast", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def cashflow_forecast(
    days: int = 30,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Прогноз остатка на N дней вперёд — текущий факт-остаток + сумма ещё
    не подтверждённых по оплате операций (payment_confirmed=False),
    сгруппированная по дате оплаты. Источник плана — сами операции (см.
    HANDOVER.md, "План/факт (ПланФакт-стиль)"), не отдельная сущность
    Планирования (та заменена этим механизмом)."""
    days = max(1, min(days, 90))
    today = date.today()
    horizon_end = today + timedelta(days=days)

    company_ids = resolve_company_ids(db, user, company_id)
    accounts = db.query(Account).filter(Account.company_id.in_(company_ids), Account.is_active.is_(True)).all()
    current_balance_rub = Decimal("0")
    for account in accounts:
        balance = _account_balance(db, account, today)
        balance_rub = convert_to_rub(db, account.currency, balance, today)
        if balance_rub is not None:
            current_balance_rub += balance_rub

    forced_project = scope_project_filter(user)
    plan_query = db.query(
        Transaction.date_odds,
        func.sum(
            case(
                (Transaction.type == TxTypeEnum.income, Transaction.amount_rub),
                else_=-Transaction.amount_rub,
            )
        ),
    ).filter(
        Transaction.company_id.in_(company_ids),
        Transaction.payment_confirmed.is_(False),
        Transaction.reclass_pair_id.is_(None),
        Transaction.date_odds > today,
        Transaction.date_odds <= horizon_end,
    )
    if forced_project:
        plan_query = plan_query.filter(Transaction.project_id == forced_project)
    by_day = dict(plan_query.group_by(Transaction.date_odds).all())

    running = current_balance_rub
    series = [{"date": today.isoformat(), "planned_flow_rub": 0.0, "projected_balance_rub": float(running)}]
    d = today + timedelta(days=1)
    while d <= horizon_end:
        flow = by_day.get(d, Decimal("0"))
        running += flow
        series.append({"date": d.isoformat(), "planned_flow_rub": float(flow), "projected_balance_rub": float(running)})
        d += timedelta(days=1)

    return {
        "as_of": today.isoformat(),
        "horizon_end": horizon_end.isoformat(),
        "current_balance_rub": float(current_balance_rub),
        "projected_balance_rub": float(running),
        "series": series,
    }


@router.get("/cashflow", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def cashflow_report(
    period: Optional[str] = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    # is_financing/is_internal_transfer исключены по той же причине, что и в
    # dashboard_summary/pnl_report — иначе кредитные линии и переводы между
    # своими же счетами раздувают "Приход/Расход" на графике по месяцам.
    query = (
        db.query(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.company_id.in_(company_ids),
            Category.is_financing.is_(False),
            Category.is_internal_transfer.is_(False),
            Transaction.payment_confirmed.is_(True),
        )
    )
    forced_project = scope_project_filter(user)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)

    if period:
        start, end = _parse_period(period)
        query = query.filter(Transaction.date_odds >= start, Transaction.date_odds <= end)

        rows = (
            query.with_entities(Category.id, Category.name, Transaction.type, func.sum(Transaction.amount_rub))
            .group_by(Category.id, Category.name, Transaction.type)
            .all()
        )
        by_category: dict = {}
        for category_id, category_name, tx_type, total in rows:
            row = by_category.setdefault(
                category_id, {"category_id": category_id, "category": category_name, "income": 0.0, "expense": 0.0}
            )
            if tx_type == TxTypeEnum.income:
                row["income"] = float(total)
            else:
                row["expense"] = float(total)
        for row in by_category.values():
            row["net"] = row["income"] - row["expense"]
        return {"period": period, "by_category": list(by_category.values())}

    month_label = func.to_char(Transaction.date_odds, "YYYY-MM").label("period")
    rows = (
        query.with_entities(month_label, Transaction.type, func.sum(Transaction.amount_rub))
        .group_by(month_label, Transaction.type)
        .order_by(month_label)
        .all()
    )
    by_month: dict = {}
    for month, tx_type, total in rows:
        row = by_month.setdefault(month, {"period": month, "income": 0.0, "expense": 0.0})
        if tx_type == TxTypeEnum.income:
            row["income"] = float(total)
        else:
            row["expense"] = float(total)
    for row in by_month.values():
        row["net"] = row["income"] - row["expense"]
    return {"by_month": list(by_month.values())}


@router.get("/pnl", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def pnl_report(
    period: Optional[str] = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start, end = _parse_period(period) if period else _current_month_bounds()

    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(Transaction).filter(
        Transaction.company_id.in_(company_ids),
        Transaction.date_odds >= start,
        Transaction.date_odds <= end,
        Transaction.accrual_confirmed.is_(True),
    )
    forced_project = scope_project_filter(user)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)

    # is_financing (кредитные линии/займы и их погашение) и is_internal_transfer
    # (переводы между своими же счетами/компаниями/физлицами) исключены из П&Л —
    # ни то, ни другое не доход и не расход бизнеса (см. dashboard_summary выше).
    revenue = (
        query.filter(Transaction.type == TxTypeEnum.income)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Category.is_financing.is_(False), Category.is_internal_transfer.is_(False))
        .with_entities(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .scalar()
    )

    group_expr = func.coalesce(Category.group_name, Category.name)
    expense_rows = (
        query.filter(Transaction.type == TxTypeEnum.expense)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Category.is_financing.is_(False), Category.is_internal_transfer.is_(False))
        .with_entities(group_expr.label("group_name"), func.sum(Transaction.amount_rub))
        .group_by(group_expr)
        .all()
    )
    expenses = [{"group": group_name, "amount": float(total)} for group_name, total in expense_rows]
    total_expense = sum(row["amount"] for row in expenses)

    return {
        "period_from": start.isoformat(),
        "period_to": end.isoformat(),
        "revenue": float(revenue),
        "expenses": expenses,
        "total_expense": total_expense,
        "net_profit": float(revenue) - total_expense,
    }


@router.get("/balance", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def balance_report(
    as_of: Optional[date] = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    as_of = as_of or date.today()
    company_ids = resolve_company_ids(db, user, company_id)

    cash_rub = Decimal("0")
    for account in db.query(Account).filter(Account.company_id.in_(company_ids)).all():
        balance = _account_balance(db, account, as_of)
        rub = convert_to_rub(db, account.currency, balance, as_of)
        if rub is not None:
            cash_rub += rub

    # Задолженность перед сотрудниками = начислено - выплачено
    # (дебиторка/предоплаты в схеме не моделируются — invoicing нет,
    # поэтому в активах учитываются только денежные средства)
    total_accrued = (
        db.query(func.coalesce(func.sum(PayrollAccrual.total), 0))
        .filter(PayrollAccrual.company_id.in_(company_ids), PayrollAccrual.period <= as_of)
        .scalar()
    )
    total_paid = (
        db.query(func.coalesce(func.sum(PayrollPayment.amount), 0))
        .filter(PayrollPayment.company_id.in_(company_ids), PayrollPayment.date <= as_of)
        .scalar()
    )
    payable_to_staff = Decimal(str(total_accrued)) - Decimal(str(total_paid))

    retained_earnings = cash_rub - payable_to_staff

    return {
        "as_of": as_of.isoformat(),
        "assets": {"cash_rub": float(cash_rub), "total_rub": float(cash_rub)},
        "liabilities": {
            "payable_to_staff_rub": float(payable_to_staff),
            "total_rub": float(payable_to_staff),
        },
        "retained_earnings_rub": float(retained_earnings),
    }


@router.get("/debt", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def debt_report(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    # Дебиторка/кредиторка по counterparties: в схеме нет отдельного реестра
    # счетов/инвойсов, поэтому считаем чистый оборот по контрагенту
    # (income − expense в amount_rub) как показатель задолженности.
    company_ids = resolve_company_ids(db, user, company_id)
    # accrual_confirmed (не payment_confirmed!) — долг создаётся самим фактом
    # неоплаты, фильтровать по оплате означало бы прятать саму задолженность
    # из отчёта. См. HANDOVER.md, "План/факт (ПланФакт-стиль)".
    query = db.query(Transaction).filter(
        Transaction.company_id.in_(company_ids),
        Transaction.counterparty_id.isnot(None),
        Transaction.accrual_confirmed.is_(True),
    )
    forced_project = scope_project_filter(user)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)

    rows = (
        query.join(Counterparty, Transaction.counterparty_id == Counterparty.id)
        .with_entities(
            Counterparty.id,
            Counterparty.name,
            Counterparty.type,
            func.sum(
                case(
                    (Transaction.type == TxTypeEnum.income, Transaction.amount_rub),
                    else_=-Transaction.amount_rub,
                )
            ),
        )
        .group_by(Counterparty.id, Counterparty.name, Counterparty.type)
        .all()
    )

    return [
        {"counterparty_id": cp_id, "name": name, "type": cp_type, "net_amount_rub": float(net_amount)}
        for cp_id, name, cp_type, net_amount in rows
    ]


def _method_confirmed_column(method: str):
    """"accrual" (по умолчанию, П&Л) | "cash" (кассовый — для отдельного
    проекта без активов/пассивов совпадает с денежным потоком, поэтому
    отдельного 3-го варианта, в отличие от ПланФакта, нет — см. HANDOVER.md,
    "Карточка проекта")."""
    return Transaction.payment_confirmed if method == "cash" else Transaction.accrual_confirmed


def _project_transactions_query(
    db: Session,
    company_ids: list[str],
    method: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> SAQuery:
    """Базовый запрос по операциям С проектом (project_id задан) — общий для
    profitability_report (список) и project_detail (карточка одного
    проекта), не дублировать SQL дважды."""
    confirmed_col = _method_confirmed_column(method)
    query = db.query(Transaction).filter(
        Transaction.company_id.in_(company_ids),
        Transaction.project_id.isnot(None),
        confirmed_col.is_(True),
    )
    if date_from:
        query = query.filter(Transaction.date_odds >= date_from)
    if date_to:
        query = query.filter(Transaction.date_odds <= date_to)
    return query


def _project_statuses(db: Session, company_ids: list[str], project_ids: list[str]) -> dict[str, str]:
    """Плановый (нет ни одной оплаченной операции) / В работе (есть хоть
    одна payment_confirmed=True — НЕЗАВИСИМО от того, каким методом сейчас
    смотрят отчёт, статус — это факт оплаты, не переключается вместе с
    методом расчёта прибыли) / Завершён (проект деактивирован —
    is_active=False сильнее "в работе")."""
    if not project_ids:
        return {}
    active_flags = dict(db.query(Project.id, Project.is_active).filter(Project.id.in_(project_ids)).all())
    has_payment = {
        pid
        for (pid,) in db.query(Transaction.project_id)
        .filter(
            Transaction.company_id.in_(company_ids),
            Transaction.project_id.in_(project_ids),
            Transaction.payment_confirmed.is_(True),
        )
        .distinct()
        .all()
    }
    statuses = {}
    for pid in project_ids:
        if not active_flags.get(pid, True):
            statuses[pid] = "closed"
        elif pid in has_payment:
            statuses[pid] = "in_progress"
        else:
            statuses[pid] = "planned"
    return statuses


@router.get("/profitability", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def profitability_report(
    project: Optional[str] = None,
    company_id: Optional[str] = None,
    method: str = "accrual",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    forced_project = scope_project_filter(user)

    # Список проектов в скоупе показываем ВЕСЬ, даже без единой операции —
    # раньше проект без движений молча исчезал из отчёта; теперь виден со
    # статусом "Плановый" (см. _project_statuses), это и есть источник
    # статусов/итоговых колонок для списка проектов в Reference.jsx.
    projects_query = db.query(Project).filter(Project.company_id.in_(company_ids))
    if forced_project:
        projects_query = projects_query.filter(Project.id == forced_project)
    elif project:
        projects_query = projects_query.filter(Project.id == project)
    projects = projects_query.all()
    project_ids = [p.id for p in projects]

    query = _project_transactions_query(db, company_ids, method, date_from, date_to)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)
    elif project:
        query = query.filter(Transaction.project_id == project)

    rows = (
        query.with_entities(Transaction.project_id, Transaction.type, func.sum(Transaction.amount_rub))
        .group_by(Transaction.project_id, Transaction.type)
        .all()
    )
    by_project: dict = {}
    for project_id, tx_type, total in rows:
        row = by_project.setdefault(project_id, {"revenue": 0.0, "expense": 0.0})
        if tx_type == TxTypeEnum.income:
            row["revenue"] = float(total)
        else:
            row["expense"] = float(total)

    statuses = _project_statuses(db, company_ids, project_ids)

    result = []
    for p in projects:
        agg = by_project.get(p.id, {"revenue": 0.0, "expense": 0.0})
        revenue, expense = agg["revenue"], agg["expense"]
        result.append(
            {
                "project_id": p.id,
                "project": p.name,
                "revenue": revenue,
                "expense": expense,
                "profit": revenue - expense,
                "margin": (revenue - expense) / revenue if revenue else None,
                "status": statuses.get(p.id, "planned"),
            }
        )

    # Операции без проекта иначе исчезают из отчёта бесследно — добавляем
    # псевдо-строку "Нераспределено". Только когда not forced_project:
    # project_manager RLS-скопирован на один проект (scope_project_filter),
    # агрегат по ВСЕМ нераспределённым операциям компании ему показывать
    # нельзя — это утечка данных за пределы разрешённого проекта.
    if not forced_project:
        confirmed_col = _method_confirmed_column(method)
        unalloc_query = db.query(Transaction).filter(
            Transaction.company_id.in_(company_ids),
            Transaction.project_id.is_(None),
            confirmed_col.is_(True),
        )
        if date_from:
            unalloc_query = unalloc_query.filter(Transaction.date_odds >= date_from)
        if date_to:
            unalloc_query = unalloc_query.filter(Transaction.date_odds <= date_to)
        unalloc_rows = (
            unalloc_query.with_entities(Transaction.type, func.sum(Transaction.amount_rub))
            .group_by(Transaction.type)
            .all()
        )
        revenue = expense = 0.0
        for tx_type, total in unalloc_rows:
            if tx_type == TxTypeEnum.income:
                revenue = float(total)
            else:
                expense = float(total)
        if revenue or expense:
            result.append(
                {
                    "project_id": None,
                    "project": "Нераспределено",
                    "revenue": revenue,
                    "expense": expense,
                    "profit": revenue - expense,
                    "margin": (revenue - expense) / revenue if revenue else None,
                    "status": None,
                }
            )
    return result


@router.get("/projects/{project_id}/detail", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def project_detail(
    project_id: str,
    method: str = "accrual",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    plan_source: str = "operations",
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Карточка проекта — см. HANDOVER.md, "Карточка проекта" (аналог
    ПланФакта, но лучше: диапазон дат, который profitability_report так и
    не научился принимать, тут есть с самого начала). Одна строка на
    проект + помесячная разбивка + расходы по статьям + план (операции или
    бюджет) — всё за один запрос, без похода на отдельную страницу П&Л."""
    company_ids = resolve_company_ids(db, user, company_id)
    forced_project = scope_project_filter(user)
    if forced_project and forced_project != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")

    project_obj = db.query(Project).filter(Project.id == project_id, Project.company_id.in_(company_ids)).first()
    if project_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")

    query = _project_transactions_query(db, company_ids, method, date_from, date_to).filter(
        Transaction.project_id == project_id
    )

    revenue = (
        query.filter(Transaction.type == TxTypeEnum.income)
        .with_entities(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .scalar()
    )
    expense = (
        query.filter(Transaction.type == TxTypeEnum.expense)
        .with_entities(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .scalar()
    )
    revenue, expense = float(revenue), float(expense)
    profit = revenue - expense
    margin = profit / revenue if revenue else None

    date_range_row = (
        db.query(func.min(Transaction.date_odds), func.max(Transaction.date_odds))
        .filter(Transaction.project_id == project_id, Transaction.company_id.in_(company_ids))
        .first()
    )
    date_range = {
        "min": date_range_row[0].isoformat() if date_range_row and date_range_row[0] else None,
        "max": date_range_row[1].isoformat() if date_range_row and date_range_row[1] else None,
    }

    month_label = func.to_char(Transaction.date_odds, "YYYY-MM").label("period")
    month_rows = (
        query.with_entities(month_label, Transaction.type, func.sum(Transaction.amount_rub))
        .group_by(month_label, Transaction.type)
        .order_by(month_label)
        .all()
    )
    by_month_map: dict = {}
    for period, tx_type, total in month_rows:
        row = by_month_map.setdefault(period, {"period": period, "revenue": 0.0, "expense": 0.0})
        if tx_type == TxTypeEnum.income:
            row["revenue"] = float(total)
        else:
            row["expense"] = float(total)
    by_month = list(by_month_map.values())

    group_expr = func.coalesce(Category.group_name, Category.name)
    category_rows = (
        query.filter(Transaction.type == TxTypeEnum.expense)
        .join(Category, Transaction.category_id == Category.id)
        .with_entities(group_expr.label("category"), func.sum(Transaction.amount_rub))
        .group_by(group_expr)
        .order_by(func.sum(Transaction.amount_rub).desc())
        .all()
    )
    by_category = [{"category": category, "amount": float(total)} for category, total in category_rows]

    project_status = _project_statuses(db, company_ids, [project_id]).get(project_id, "planned")

    plan = {"revenue": 0.0, "expense": 0.0}
    if plan_source == "budget":
        budget_rows = (
            db.query(Category.type, func.sum(ProjectBudgetLine.amount))
            .join(Category, ProjectBudgetLine.category_id == Category.id)
            .filter(ProjectBudgetLine.project_id == project_id)
            .group_by(Category.type)
            .all()
        )
        for tx_type, total in budget_rows:
            if tx_type == TxTypeEnum.income:
                plan["revenue"] = float(total)
            else:
                plan["expense"] = float(total)
    else:
        # "Операции" — тот же приём, что уже используется в payment_calendar:
        # план — это ещё не подтверждённые по начислению операции проекта.
        plan_rows = (
            db.query(Transaction.type, func.sum(Transaction.amount_rub))
            .filter(
                Transaction.company_id.in_(company_ids),
                Transaction.project_id == project_id,
                Transaction.accrual_confirmed.is_(False),
            )
            .group_by(Transaction.type)
            .all()
        )
        for tx_type, total in plan_rows:
            if tx_type == TxTypeEnum.income:
                plan["revenue"] = float(total)
            else:
                plan["expense"] = float(total)

    return {
        "project_id": project_obj.id,
        "project_name": project_obj.name,
        "status": project_status,
        "date_range": date_range,
        "revenue": revenue,
        "expense": expense,
        "profit": profit,
        "margin": margin,
        "by_month": by_month,
        "by_category": by_category,
        "plan_source": plan_source,
        "plan": plan,
    }


@router.get("/payment-calendar", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def payment_calendar(
    quarter: Optional[str] = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    year = date.today().year
    if quarter:
        try:
            year = int(quarter.split("-")[0])
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="quarter должен быть в формате YYYY или YYYY-Q#",
            )

    company_ids = resolve_company_ids(db, user, company_id)
    forced_project = scope_project_filter(user)
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)

    # "План" и "факт" — теперь одна и та же таблица Transaction, различаются
    # только флагом accrual_confirmed (см. HANDOVER.md, "План/факт
    # (ПланФакт-стиль)") — раньше план брался из отдельной сущности
    # Планирования, та этим механизмом заменена.
    plan_query = db.query(Transaction).filter(
        Transaction.company_id.in_(company_ids),
        Transaction.date_odds >= year_start,
        Transaction.date_odds <= year_end,
        Transaction.accrual_confirmed.is_(False),
        Transaction.reclass_pair_id.is_(None),
    )
    fact_query = db.query(Transaction).filter(
        Transaction.company_id.in_(company_ids),
        Transaction.date_odds >= year_start,
        Transaction.date_odds <= year_end,
        Transaction.accrual_confirmed.is_(True),
    )
    if forced_project:
        plan_query = plan_query.filter(Transaction.project_id == forced_project)
        fact_query = fact_query.filter(Transaction.project_id == forced_project)

    def _empty_quarters():
        return {q: {"plan": 0.0, "fact": 0.0} for q in range(1, 5)}

    by_category: dict = {}

    for tx in plan_query.all():
        row = by_category.setdefault(tx.category_id, _empty_quarters())
        signed = float(tx.amount_rub) if tx.type == TxTypeEnum.income else -float(tx.amount_rub)
        row[_quarter_of(tx.date_odds)]["plan"] += signed

    for tx in fact_query.all():
        row = by_category.setdefault(tx.category_id, _empty_quarters())
        signed = float(tx.amount_rub) if tx.type == TxTypeEnum.income else -float(tx.amount_rub)
        row[_quarter_of(tx.date_odds)]["fact"] += signed

    category_names = {c.id: c.name for c in db.query(Category).filter(Category.company_id.in_(company_ids)).all()}
    rows = []
    for category_id, quarters in by_category.items():
        rows.append(
            {
                "category_id": category_id,
                "category": category_names.get(category_id, ""),
                "quarters": [
                    {"quarter": q, "plan": v["plan"], "fact": v["fact"], "deviation": v["fact"] - v["plan"]}
                    for q, v in quarters.items()
                ],
            }
        )

    return {"year": year, "rows": rows}
