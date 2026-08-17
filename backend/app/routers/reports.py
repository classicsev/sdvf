from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

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
    Planning,
    Project,
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
        .filter(Transaction.account_id == account.id, Transaction.date_odds <= as_of)
        .scalar()
    )
    return Decimal(str(account.opening_balance)) + (flow or Decimal("0"))


@router.get("/dashboard-summary", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def dashboard_summary(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    today = date.today()
    period_from, period_to = _current_month_bounds()
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
    for account in accounts:
        balance = _account_balance(db, account, today)
        balance_rub = convert_to_rub(db, account.currency, balance, today)
        if balance_rub is not None:
            total_balance_rub += balance_rub
            balance_by_company[account.company_id] = balance_by_company.get(account.company_id, Decimal("0")) + balance_rub
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

    forced_project = scope_project_filter(user)
    # is_financing (кредитные линии/займы и их погашение) — не доход и не расход
    # бизнеса ни при УСН-доходы, ни при ОСН (см. models.py::Category.is_financing),
    # поэтому не входит в "Приход/Расход" — сами операции остаются в списке
    # транзакций и в остатке счёта, просто не искажают эти сводные цифры.
    period_query = (
        db.query(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.company_id.in_(company_ids),
            Transaction.date_odds >= period_from,
            Transaction.date_odds <= period_to,
            Category.is_financing.is_(False),
        )
    )
    if forced_project:
        period_query = period_query.filter(Transaction.project_id == forced_project)

    period_income = (
        period_query.filter(Transaction.type == TxTypeEnum.income)
        .with_entities(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .scalar()
    )
    period_expense = (
        period_query.filter(Transaction.type == TxTypeEnum.expense)
        .with_entities(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .scalar()
    )

    income_by_company = dict(
        period_query.filter(Transaction.type == TxTypeEnum.income)
        .with_entities(Transaction.company_id, func.coalesce(func.sum(Transaction.amount_rub), 0))
        .group_by(Transaction.company_id)
        .all()
    )
    expense_by_company = dict(
        period_query.filter(Transaction.type == TxTypeEnum.expense)
        .with_entities(Transaction.company_id, func.coalesce(func.sum(Transaction.amount_rub), 0))
        .group_by(Transaction.company_id)
        .all()
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

    return {
        "accounts": account_rows,
        "total_balance_rub": float(total_balance_rub),
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "period_income_rub": float(period_income),
        "period_expense_rub": float(period_expense),
        "net_flow_rub": float(period_income) - float(period_expense),
        "by_company": by_company,
    }


@router.get("/cashflow", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def cashflow_report(
    period: Optional[str] = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(Transaction).filter(Transaction.company_id.in_(company_ids))
    forced_project = scope_project_filter(user)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)

    if period:
        start, end = _parse_period(period)
        query = query.filter(Transaction.date_odds >= start, Transaction.date_odds <= end)

        rows = (
            query.join(Category, Transaction.category_id == Category.id)
            .with_entities(Category.id, Category.name, Transaction.type, func.sum(Transaction.amount_rub))
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
        Transaction.company_id.in_(company_ids), Transaction.date_odds >= start, Transaction.date_odds <= end
    )
    forced_project = scope_project_filter(user)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)

    # is_financing (кредитные линии/займы и их погашение) исключены из П&Л — не
    # доход и не расход бизнеса ни при УСН-доходы, ни при ОСН (см.
    # models.py::Category.is_financing и dashboard_summary выше).
    revenue = (
        query.filter(Transaction.type == TxTypeEnum.income)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Category.is_financing.is_(False))
        .with_entities(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .scalar()
    )

    group_expr = func.coalesce(Category.group_name, Category.name)
    expense_rows = (
        query.filter(Transaction.type == TxTypeEnum.expense)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Category.is_financing.is_(False))
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
    query = db.query(Transaction).filter(
        Transaction.company_id.in_(company_ids), Transaction.counterparty_id.isnot(None)
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


@router.get("/profitability", dependencies=[Depends(require_roles(REPORT_VIEWERS)), FINANCE_MODULE])
def profitability_report(
    project: Optional[str] = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(Transaction).filter(
        Transaction.company_id.in_(company_ids), Transaction.project_id.isnot(None)
    )

    forced_project = scope_project_filter(user)
    if forced_project:
        query = query.filter(Transaction.project_id == forced_project)
    elif project:
        query = query.filter(Transaction.project_id == project)

    rows = (
        query.join(Project, Transaction.project_id == Project.id)
        .with_entities(Project.id, Project.name, Transaction.type, func.sum(Transaction.amount_rub))
        .group_by(Project.id, Project.name, Transaction.type)
        .all()
    )

    by_project: dict = {}
    for project_id, name, tx_type, total in rows:
        row = by_project.setdefault(
            project_id, {"project_id": project_id, "project": name, "revenue": 0.0, "expense": 0.0}
        )
        if tx_type == TxTypeEnum.income:
            row["revenue"] = float(total)
        else:
            row["expense"] = float(total)

    result = []
    for row in by_project.values():
        row["profit"] = row["revenue"] - row["expense"]
        row["margin"] = row["profit"] / row["revenue"] if row["revenue"] else None
        result.append(row)
    return result


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

    plan_query = db.query(Planning).filter(
        Planning.company_id.in_(company_ids), Planning.scheduled_date >= year_start, Planning.scheduled_date <= year_end
    )
    fact_query = db.query(Transaction).filter(
        Transaction.company_id.in_(company_ids), Transaction.date_odds >= year_start, Transaction.date_odds <= year_end
    )
    if forced_project:
        plan_query = plan_query.filter(Planning.project_id == forced_project)
        fact_query = fact_query.filter(Transaction.project_id == forced_project)

    def _empty_quarters():
        return {q: {"plan": 0.0, "fact": 0.0} for q in range(1, 5)}

    by_category: dict = {}

    for plan in plan_query.all():
        row = by_category.setdefault(plan.category_id, _empty_quarters())
        row[_quarter_of(plan.scheduled_date)]["plan"] += float(plan.amount)

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
