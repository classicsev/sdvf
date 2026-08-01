from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import Planning, RoleEnum
from app.schemas import PlanningIn, PlanningOut
from app.utils import get_or_404

router = APIRouter(tags=["planning"])

ADMIN_ONLY = [RoleEnum.admin]


@router.get("/planning", response_model=list[PlanningOut], dependencies=[Depends(get_current_user)])
def list_planning(project: Optional[str] = None, year: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Planning)
    if project:
        query = query.filter(Planning.project_id == project)
    if year:
        query = query.filter(Planning.scheduled_date >= date(year, 1, 1), Planning.scheduled_date <= date(year, 12, 31))
    return query.order_by(Planning.scheduled_date.desc()).all()


@router.post("/planning", response_model=PlanningOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def create_planning(payload: PlanningIn, db: Session = Depends(get_db)):
    obj = Planning(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/planning/{planning_id}", response_model=PlanningOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def update_planning(planning_id: str, payload: PlanningIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Planning, planning_id, "Плановая запись не найдена")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/planning/{planning_id}", dependencies=[Depends(require_roles(ADMIN_ONLY))])
def delete_planning(planning_id: str, db: Session = Depends(get_db)):
    obj = get_or_404(db, Planning, planning_id, "Плановая запись не найдена")
    db.delete(obj)
    db.commit()
    return {"deleted": True}
