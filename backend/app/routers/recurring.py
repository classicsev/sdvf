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
from app.models import RecurringTemplate, RoleEnum, User
from app.schemas import RecurringTemplateIn, RecurringTemplateOut
from app.utils import get_or_404_accessible

router = APIRouter(prefix="/recurring-templates", tags=["recurring-templates"])

# Та же строгость, что у бюджетов/ОС (см. company_budget.py/fixed_assets.py) —
# только admin заводит/меняет шаблоны, которые сами создают операции.
ADMIN_ONLY = [RoleEnum.admin]
FINANCE_MODULE = Depends(require_module("finance"))


@router.get("", response_model=list[RecurringTemplateOut], dependencies=[FINANCE_MODULE])
def list_recurring_templates(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return (
        db.query(RecurringTemplate)
        .filter(RecurringTemplate.company_id.in_(company_ids))
        .order_by(RecurringTemplate.next_run_date)
        .all()
    )


@router.post("", response_model=RecurringTemplateOut, dependencies=[FINANCE_MODULE])
def create_recurring_template(
    payload: RecurringTemplateIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    obj = RecurringTemplate(**payload.model_dump(), company_id=target, created_by=user.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{template_id}", response_model=RecurringTemplateOut, dependencies=[FINANCE_MODULE])
def update_recurring_template(
    template_id: str, payload: RecurringTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = get_or_404_accessible(
        db, RecurringTemplate, template_id, get_accessible_company_ids(db, user), "Шаблон не найден"
    )
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{template_id}", dependencies=[FINANCE_MODULE])
def delete_recurring_template(template_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = get_or_404_accessible(
        db, RecurringTemplate, template_id, get_accessible_company_ids(db, user), "Шаблон не найден"
    )
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    db.delete(obj)
    db.commit()
    return {"deleted": True}
