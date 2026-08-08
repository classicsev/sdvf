from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_module, require_roles
from app.database import get_db
from app.models import Planning, RoleEnum, User
from app.schemas import PlanningIn, PlanningOut
from app.utils import get_or_404

router = APIRouter(tags=["planning"])

ADMIN_ONLY = [RoleEnum.admin]
FINANCE_MODULE = Depends(require_module("finance"))


@router.get("/planning", response_model=list[PlanningOut], dependencies=[FINANCE_MODULE])
def list_planning(
    project: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Planning).filter(Planning.company_id == user.company_id)
    if project:
        query = query.filter(Planning.project_id == project)
    if year:
        query = query.filter(Planning.scheduled_date >= date(year, 1, 1), Planning.scheduled_date <= date(year, 12, 31))
    return query.order_by(Planning.scheduled_date.desc()).all()


@router.post(
    "/planning", response_model=PlanningOut, dependencies=[Depends(require_roles(ADMIN_ONLY)), FINANCE_MODULE]
)
def create_planning(payload: PlanningIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Planning(**payload.model_dump(), company_id=user.company_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/planning/{planning_id}",
    response_model=PlanningOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), FINANCE_MODULE],
)
def update_planning(
    planning_id: str, payload: PlanningIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = get_or_404(db, Planning, planning_id, "Плановая запись не найдена", company_id=user.company_id)
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/planning/{planning_id}",
    dependencies=[Depends(require_roles(ADMIN_ONLY)), FINANCE_MODULE],
)
def delete_planning(planning_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = get_or_404(db, Planning, planning_id, "Плановая запись не найдена", company_id=user.company_id)
    db.delete(obj)
    db.commit()
    return {"deleted": True}
