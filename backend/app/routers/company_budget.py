from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import check_company_role, get_current_user, require_module, resolve_company_ids, resolve_write_company_id
from app.database import get_db
from app.models import Category, CompanyBudgetLine, RoleEnum, Transaction, User
from app.schemas import CompanyBudgetLineIn, CompanyBudgetLineOut
from app.utils import get_or_404_accessible

router = APIRouter(tags=["company-budget"])

# БДДС/БДР — та же строгость, что бюджет проекта (см. reference.py) — только
# admin ставит компанийные плановые цифры.
ADMIN_ONLY = [RoleEnum.admin]
FINANCE_MODULE = Depends(require_module("finance"))


@router.get("/company-budget-lines", response_model=list[CompanyBudgetLineOut], dependencies=[FINANCE_MODULE])
def list_company_budget_lines(
    period: str,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    return (
        db.query(CompanyBudgetLine)
        .filter(CompanyBudgetLine.company_id.in_(company_ids), CompanyBudgetLine.period == period)
        .all()
    )


@router.post("/company-budget-lines", response_model=list[CompanyBudgetLineOut], dependencies=[FINANCE_MODULE])
def replace_company_budget_lines(
    period: str,
    payload: list[CompanyBudgetLineIn],
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Сохраняет весь план на этот period сразу — тот же upsert-паттерн, что
    у бюджета проекта (см. reference.py::replace_project_budget_lines)."""
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)

    existing = {
        line.category_id: line
        for line in db.query(CompanyBudgetLine)
        .filter(CompanyBudgetLine.company_id == target, CompanyBudgetLine.period == period)
        .all()
    }
    seen_category_ids = set()
    for item in payload:
        seen_category_ids.add(item.category_id)
        line = existing.get(item.category_id)
        if line:
            line.amount = item.amount
        else:
            db.add(CompanyBudgetLine(company_id=target, category_id=item.category_id, period=period, amount=item.amount))
    for category_id, line in existing.items():
        if category_id not in seen_category_ids:
            db.delete(line)
    db.commit()
    return (
        db.query(CompanyBudgetLine)
        .filter(CompanyBudgetLine.company_id == target, CompanyBudgetLine.period == period)
        .all()
    )


@router.delete("/company-budget-lines/{line_id}", dependencies=[FINANCE_MODULE])
def delete_company_budget_line(line_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    line = get_or_404_accessible(db, CompanyBudgetLine, line_id, resolve_company_ids(db, user, None), "Строка бюджета не найдена")
    check_company_role(db, user, line.company_id, ADMIN_ONLY)
    db.delete(line)
    db.commit()
    return {"deleted": True}


@router.get("/reports/company-budget", dependencies=[FINANCE_MODULE])
def company_budget_report(
    period: str,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """План/факт по статьям на месяц (БДДС/БДР) — план из CompanyBudgetLine,
    факт — те же фильтры, что _income_expense_for_range в reports.py
    (is_financing/is_internal_transfer исключены, accrual_confirmed=True),
    но сгруппированные по статье, а не свёрнутые в одну сумму."""
    company_ids = resolve_company_ids(db, user, company_id)
    year, month = (int(p) for p in period.split("-"))
    period_from = date(year, month, 1)
    period_to = date(year + (month // 12), (month % 12) + 1, 1)
    period_to = date.fromordinal(period_to.toordinal() - 1)

    plan_rows = (
        db.query(CompanyBudgetLine)
        .filter(CompanyBudgetLine.company_id.in_(company_ids), CompanyBudgetLine.period == period)
        .all()
    )
    plan_by_category = {line.category_id: float(line.amount) for line in plan_rows}

    fact_rows = (
        db.query(Category.id, Category.name, Category.type, func.coalesce(func.sum(Transaction.amount_rub), 0))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            Transaction.company_id.in_(company_ids),
            Transaction.date_odds >= period_from,
            Transaction.date_odds <= period_to,
            Category.is_financing.is_(False),
            Category.is_internal_transfer.is_(False),
            Transaction.accrual_confirmed.is_(True),
        )
        .group_by(Category.id, Category.name, Category.type)
        .all()
    )
    fact_by_category = {row[0]: float(row[3]) for row in fact_rows}
    name_by_category = {row[0]: row[1] for row in fact_rows}
    type_by_category = {row[0]: row[2] for row in fact_rows}

    category_ids = set(plan_by_category) | set(fact_by_category)
    if category_ids - set(name_by_category):
        for c in db.query(Category).filter(Category.id.in_(category_ids - set(name_by_category))).all():
            name_by_category[c.id] = c.name
            type_by_category[c.id] = c.type

    lines = [
        {
            "category_id": cid,
            "category_name": name_by_category.get(cid, ""),
            "type": type_by_category.get(cid).value if type_by_category.get(cid) else None,
            "plan_rub": plan_by_category.get(cid, 0.0),
            "fact_rub": fact_by_category.get(cid, 0.0),
        }
        for cid in category_ids
    ]
    lines.sort(key=lambda l: l["category_name"])

    return {
        "period": period,
        "lines": lines,
        "plan_total_rub": sum(plan_by_category.values()),
        "fact_total_rub": sum(fact_by_category.values()),
    }
