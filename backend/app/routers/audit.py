from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import AuditLog, RoleEnum, User

router = APIRouter(tags=["audit"])

PAYROLL_ENTITY_TYPES = ["payroll_accrual", "payroll_payment"]


@router.get(
    "/audit-log",
    dependencies=[Depends(require_roles([RoleEnum.admin, RoleEnum.payroll_operator]))],
)
def list_audit_log(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(AuditLog)
    if user.role == RoleEnum.payroll_operator:
        query = query.filter(AuditLog.entity_type.in_(PAYROLL_ENTITY_TYPES))
    return query.order_by(AuditLog.created_at.desc()).all()
