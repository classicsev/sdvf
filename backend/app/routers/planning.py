from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids,
    resolve_write_company_id,
)
from app.database import get_db
from app.models import Category, Planning, Project, RoleEnum, User
from app.reference_scope import get_visible_or_404
from app.schemas import PlanningIn, PlanningOut
from app.utils import get_or_404_accessible

router = APIRouter(tags=["planning"])

ADMIN_ONLY = [RoleEnum.admin]
FINANCE_MODULE = Depends(require_module("finance"))


@router.get("/planning", response_model=list[PlanningOut], dependencies=[FINANCE_MODULE])
def list_planning(
    company_id: Optional[str] = None,
    project: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(Planning).filter(Planning.company_id.in_(company_ids))
    if project:
        query = query.filter(Planning.project_id == project)
    if year:
        query = query.filter(Planning.scheduled_date >= date(year, 1, 1), Planning.scheduled_date <= date(year, 12, 31))
    return query.order_by(Planning.scheduled_date.desc()).all()


@router.post("/planning", response_model=PlanningOut, dependencies=[FINANCE_MODULE])
def create_planning(
    payload: PlanningIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    get_visible_or_404(db, Category, payload.category_id, [target], "Статья не найдена")
    if payload.project_id:
        get_visible_or_404(db, Project, payload.project_id, [target], "Проект не найден")
    obj = Planning(**payload.model_dump(), company_id=target)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/planning/{planning_id}", response_model=PlanningOut, dependencies=[FINANCE_MODULE])
def update_planning(
    planning_id: str, payload: PlanningIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = get_or_404_accessible(
        db, Planning, planning_id, get_accessible_company_ids(db, user), "Плановая запись не найдена"
    )
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    get_visible_or_404(db, Category, payload.category_id, [obj.company_id], "Статья не найдена")
    if payload.project_id:
        get_visible_or_404(db, Project, payload.project_id, [obj.company_id], "Проект не найден")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/planning/{planning_id}", dependencies=[FINANCE_MODULE])
def delete_planning(planning_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = get_or_404_accessible(
        db, Planning, planning_id, get_accessible_company_ids(db, user), "Плановая запись не найдена"
    )
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    db.delete(obj)
    db.commit()
    return {"deleted": True}
