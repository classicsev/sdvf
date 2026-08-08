from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import get_current_user, require_module, require_roles
from app.crypto import decrypt_field, encrypt_field
from app.database import get_db
from app.models import Employee, PayrollAccrual, PayrollPayment, RoleEnum, User
from app.schemas import (
    EmployeeIn,
    EmployeeOut,
    PayrollAccrualIn,
    PayrollAccrualOut,
    PayrollPaymentIn,
    PayrollPaymentOut,
)
from app.utils import get_or_404

router = APIRouter(prefix="/payroll", tags=["payroll"])

# Изолированный контур: только admin и payroll_operator. Operator и project_manager
# сюда не заходят вообще (см. матрицу прав в README).
PAYROLL_EDITORS = [RoleEnum.admin, RoleEnum.payroll_operator]

# viewer получает только агрегированную сводку без ФИО/реквизитов (см. README);
# admin/payroll_operator и так видят всё через детальные эндпоинты выше.
SUMMARY_VIEWERS = [RoleEnum.admin, RoleEnum.payroll_operator, RoleEnum.viewer]


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _parse_period(period: str) -> tuple[date, date]:
    try:
        year_str, month_str = period.split("-")
        year, month = int(year_str), int(month_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="period должен быть в формате YYYY-MM")
    return date(year, month, 1), _month_end(year, month)


def _get_or_404(db: Session, model, entity_id: str, detail: str, company_id: str):
    return get_or_404(db, model, entity_id, detail, company_id=company_id)


def _employee_to_out(emp: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=emp.id,
        full_name=emp.full_name,
        department=emp.department,
        position=emp.position,
        employment_type=emp.employment_type,
        status=emp.status,
        bank_details=decrypt_field(emp.bank_details_encrypted) if emp.bank_details_encrypted else None,
    )


@router.get(
    "/employees",
    response_model=list[EmployeeOut],
    dependencies=[Depends(require_roles(PAYROLL_EDITORS)), Depends(require_module("finance"))],
)
def list_employees(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_employee_to_out(e) for e in db.query(Employee).filter(Employee.company_id == user.company_id).all()]


@router.post(
    "/employees",
    response_model=EmployeeOut,
    dependencies=[Depends(require_roles(PAYROLL_EDITORS)), Depends(require_module("finance"))],
)
def create_employee(payload: EmployeeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = payload.model_dump()
    bank_details = data.pop("bank_details", None)
    obj = Employee(
        **data,
        company_id=user.company_id,
        bank_details_encrypted=encrypt_field(bank_details) if bank_details else None,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _employee_to_out(obj)


@router.patch(
    "/employees/{employee_id}",
    response_model=EmployeeOut,
    dependencies=[Depends(require_roles(PAYROLL_EDITORS)), Depends(require_module("finance"))],
)
def update_employee(
    employee_id: str, payload: EmployeeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, Employee, employee_id, "Сотрудник не найден", user.company_id)
    data = payload.model_dump()
    bank_details = data.pop("bank_details", None)
    for k, v in data.items():
        setattr(obj, k, v)
    obj.bank_details_encrypted = encrypt_field(bank_details) if bank_details else None
    db.commit()
    db.refresh(obj)
    return _employee_to_out(obj)


@router.delete(
    "/employees/{employee_id}",
    dependencies=[Depends(require_roles(PAYROLL_EDITORS)), Depends(require_module("finance"))],
)
def delete_employee(employee_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # TODO: запретить удаление, если у сотрудника уже есть начисления/выплаты —
    # предложить деактивировать (status="dismissed"), а не удалять физически
    obj = _get_or_404(db, Employee, employee_id, "Сотрудник не найден", user.company_id)
    db.delete(obj)
    db.commit()
    return {"deleted": True}


@router.get(
    "/accruals",
    response_model=list[PayrollAccrualOut],
    dependencies=[Depends(require_roles(PAYROLL_EDITORS)), Depends(require_module("finance"))],
)
def list_accruals(period: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(PayrollAccrual).filter(PayrollAccrual.company_id == user.company_id)
    if period:
        start, end = _parse_period(period)
        query = query.filter(PayrollAccrual.period >= start, PayrollAccrual.period <= end)
    return query.order_by(PayrollAccrual.period.desc()).all()


@router.post(
    "/accruals",
    response_model=PayrollAccrualOut,
    dependencies=[Depends(require_roles(PAYROLL_EDITORS)), Depends(require_module("finance"))],
)
def create_accrual(
    payload: PayrollAccrualIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_or_404(db, Employee, payload.employee_id, "Сотрудник не найден", user.company_id)

    total = payload.salary + payload.bonus - payload.deductions
    accrual = PayrollAccrual(**payload.model_dump(), company_id=user.company_id, total=total)
    db.add(accrual)
    db.commit()
    db.refresh(accrual)
    log_action(db, user, action="create", entity_type="payroll_accrual", entity_id=accrual.id)
    return accrual


@router.get(
    "/payments",
    response_model=list[PayrollPaymentOut],
    dependencies=[Depends(require_roles(PAYROLL_EDITORS)), Depends(require_module("finance"))],
)
def list_payments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(PayrollPayment)
        .filter(PayrollPayment.company_id == user.company_id)
        .order_by(PayrollPayment.date.desc())
        .all()
    )


@router.post(
    "/payments",
    response_model=PayrollPaymentOut,
    dependencies=[Depends(require_roles(PAYROLL_EDITORS)), Depends(require_module("finance"))],
)
def create_payment(
    payload: PayrollPaymentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_or_404(db, Employee, payload.employee_id, "Сотрудник не найден", user.company_id)
    if payload.accrual_id:
        _get_or_404(db, PayrollAccrual, payload.accrual_id, "Начисление не найдено", user.company_id)

    payment = PayrollPayment(**payload.model_dump(), company_id=user.company_id)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    log_action(db, user, action="create", entity_type="payroll_payment", entity_id=payment.id)
    return payment


@router.get(
    "/summary-for-viewer",
    dependencies=[Depends(require_roles(SUMMARY_VIEWERS)), Depends(require_module("finance"))],
)
def payroll_summary_for_viewer(
    period: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    # Агрегированная сводка ФОТ без ФИО и реквизитов — доступна viewer
    # (плюс admin/payroll_operator, которым и так открыты детальные эндпоинты).
    accrual_query = db.query(PayrollAccrual).filter(PayrollAccrual.company_id == user.company_id)
    payment_query = db.query(PayrollPayment).filter(PayrollPayment.company_id == user.company_id)

    if period:
        start, end = _parse_period(period)
        accrual_query = accrual_query.filter(PayrollAccrual.period >= start, PayrollAccrual.period <= end)
        payment_query = payment_query.filter(PayrollPayment.date >= start, PayrollPayment.date <= end)

    total_accrued = accrual_query.with_entities(func.coalesce(func.sum(PayrollAccrual.total), 0)).scalar()
    total_paid = payment_query.with_entities(func.coalesce(func.sum(PayrollPayment.amount), 0)).scalar()
    employees_count = accrual_query.with_entities(func.count(func.distinct(PayrollAccrual.employee_id))).scalar()

    return {
        "period": period,
        "employees_count": employees_count,
        "total_accrued": float(total_accrued),
        "total_paid": float(total_paid),
        "outstanding": float(total_accrued) - float(total_paid),
    }
