from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, resolve_company_ids_with_role
from app.database import get_db
from app.models import AuditLog, CompanyMember, RoleEnum, User

router = APIRouter(tags=["audit"])

PAYROLL_ENTITY_TYPES = ["payroll_accrual", "payroll_payment"]
VIEWERS = [RoleEnum.admin, RoleEnum.payroll_operator]


@router.get("/audit-log")
def list_audit_log(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids_with_role(db, user, company_id, VIEWERS)

    # payroll_operator видит только записи ФОТ, admin — всё; роль проверяется
    # per-company (см. план "Мульти-компании") — один и тот же пользователь
    # может быть admin в одной компании и payroll_operator в другой, поэтому
    # фильтр по entity_type применяется по каждой компании отдельно, не глобально.
    roles_by_company = dict(
        db.query(CompanyMember.company_id, CompanyMember.role)
        .filter(CompanyMember.user_id == user.id, CompanyMember.company_id.in_(company_ids))
        .all()
    )
    payroll_only_ids = [cid for cid in company_ids if roles_by_company.get(cid) == RoleEnum.payroll_operator]
    full_access_ids = [cid for cid in company_ids if cid not in payroll_only_ids]

    conditions = []
    if full_access_ids:
        conditions.append(AuditLog.company_id.in_(full_access_ids))
    if payroll_only_ids:
        conditions.append(
            and_(AuditLog.company_id.in_(payroll_only_ids), AuditLog.entity_type.in_(PAYROLL_ENTITY_TYPES))
        )

    query = db.query(AuditLog).filter(or_(*conditions))
    return query.order_by(AuditLog.created_at.desc()).all()
