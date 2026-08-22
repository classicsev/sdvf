from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids_with_role,
    resolve_write_company_id,
)
from app.crypto import decrypt_field, encrypt_field
from app.database import get_db
from app.models import Account, Employee, PayrollAccrual, PayrollPayment, Project, RoleEnum, User
from app.schemas import (
    EmployeeIn,
    EmployeeOut,
    MoveCompanyIn,
    PayrollAccrualIn,
    PayrollAccrualOut,
    PayrollPaymentIn,
    PayrollPaymentOut,
)
from app.reference_scope import get_visible_or_404
from app.utils import get_or_404_accessible, move_to_company

router = APIRouter(prefix="/payroll", tags=["payroll"])

# Изолированный контур: только admin и payroll_operator. Operator и project_manager
# сюда не заходят вообще (см. матрицу прав в README).
PAYROLL_EDITORS = [RoleEnum.admin, RoleEnum.payroll_operator]
# Перенос между компаниями — только admin (и в исходной, и в целевой), как и у
# справочников (см. reference.py::_move_to_company) — более чувствительное
# действие, чем обычное редактирование, payroll_operator сюда не допущен.
ADMIN_ONLY = [RoleEnum.admin]

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


def _get_or_404(db: Session, user: User, model, entity_id: str, detail: str):
    return get_or_404_accessible(db, model, entity_id, get_accessible_company_ids(db, user), detail)


def _employee_to_out(emp: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=emp.id,
        company_id=emp.company_id,
        full_name=emp.full_name,
        aliases=emp.aliases,
        department=emp.department,
        position=emp.position,
        employment_type=emp.employment_type,
        status=emp.status,
        bank_details=decrypt_field(emp.bank_details_encrypted) if emp.bank_details_encrypted else None,
    )


@router.get("/employees", response_model=list[EmployeeOut], dependencies=[Depends(require_module("finance"))])
def list_employees(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids_with_role(db, user, company_id, PAYROLL_EDITORS)
    return [_employee_to_out(e) for e in db.query(Employee).filter(Employee.company_id.in_(company_ids)).all()]


@router.post("/employees", response_model=EmployeeOut, dependencies=[Depends(require_module("finance"))])
def create_employee(
    payload: EmployeeIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, PAYROLL_EDITORS)
    data = payload.model_dump()
    bank_details = data.pop("bank_details", None)
    obj = Employee(
        **data,
        company_id=target,
        bank_details_encrypted=encrypt_field(bank_details) if bank_details else None,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _employee_to_out(obj)


@router.patch(
    "/employees/{employee_id}", response_model=EmployeeOut, dependencies=[Depends(require_module("finance"))]
)
def update_employee(
    employee_id: str, payload: EmployeeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, user, Employee, employee_id, "Сотрудник не найден")
    check_company_role(db, user, obj.company_id, PAYROLL_EDITORS)
    data = payload.model_dump()
    bank_details = data.pop("bank_details", None)
    for k, v in data.items():
        setattr(obj, k, v)
    obj.bank_details_encrypted = encrypt_field(bank_details) if bank_details else None
    db.commit()
    db.refresh(obj)
    return _employee_to_out(obj)


@router.delete("/employees/{employee_id}", dependencies=[Depends(require_module("finance"))])
def delete_employee(employee_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, user, Employee, employee_id, "Сотрудник не найден")
    check_company_role(db, user, obj.company_id, PAYROLL_EDITORS)
    # Физическое удаление уронило бы FK-констрейнт, если у сотрудника уже есть
    # начисления/выплаты (история должна остаться) — тогда вместо удаления
    # переводим в "dismissed" (тот же паттерн, что и is_active=False для
    # статей/проектов/счетов/контрагентов, см. utils.delete_or_deactivate —
    # Employee использует свободный status, а не булев флаг, поэтому не через
    # общий хелпер).
    in_use = (
        db.query(PayrollAccrual).filter(PayrollAccrual.employee_id == obj.id).first() is not None
        or db.query(PayrollPayment).filter(PayrollPayment.employee_id == obj.id).first() is not None
    )
    if in_use:
        obj.status = "dismissed"
        db.commit()
        return {"deleted": False, "deactivated": True}
    db.delete(obj)
    db.commit()
    return {"deleted": True, "deactivated": False}


@router.post(
    "/employees/{employee_id}/toggle-status",
    response_model=EmployeeOut,
    dependencies=[Depends(require_module("finance"))],
)
def toggle_employee_status(
    employee_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, user, Employee, employee_id, "Сотрудник не найден")
    check_company_role(db, user, obj.company_id, PAYROLL_EDITORS)
    obj.status = "active" if obj.status == "dismissed" else "dismissed"
    db.commit()
    db.refresh(obj)
    return _employee_to_out(obj)


@router.patch(
    "/employees/{employee_id}/company",
    response_model=EmployeeOut,
    dependencies=[Depends(require_module("finance"))],
)
def move_employee_company(
    employee_id: str,
    payload: MoveCompanyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_or_404(db, user, Employee, employee_id, "Сотрудник не найден")
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    check_company_role(db, user, payload.company_id, ADMIN_ONLY)
    move_to_company(db, obj, payload.company_id, [(PayrollAccrual, "employee_id"), (PayrollPayment, "employee_id")])
    db.refresh(obj)
    return _employee_to_out(obj)


@router.get("/accruals", response_model=list[PayrollAccrualOut], dependencies=[Depends(require_module("finance"))])
def list_accruals(
    period: str | None = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids_with_role(db, user, company_id, PAYROLL_EDITORS)
    query = db.query(PayrollAccrual).filter(PayrollAccrual.company_id.in_(company_ids))
    if period:
        start, end = _parse_period(period)
        query = query.filter(PayrollAccrual.period >= start, PayrollAccrual.period <= end)
    return query.order_by(PayrollAccrual.period.desc()).all()


@router.post("/accruals", response_model=PayrollAccrualOut, dependencies=[Depends(require_module("finance"))])
def create_accrual(
    payload: PayrollAccrualIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Компания начисления определяется по сотруднику — эти два всегда в одной
    # компании (нельзя начислить сотруднику другого юрлица).
    employee = _get_or_404(db, user, Employee, payload.employee_id, "Сотрудник не найден")
    check_company_role(db, user, employee.company_id, PAYROLL_EDITORS)
    if payload.project_id:
        get_visible_or_404(db, Project, payload.project_id, [employee.company_id], "Проект не найден")

    total = payload.salary + payload.bonus - payload.deductions
    accrual = PayrollAccrual(**payload.model_dump(), company_id=employee.company_id, total=total)
    db.add(accrual)
    db.commit()
    db.refresh(accrual)
    log_action(db, user, action="create", entity_type="payroll_accrual", entity_id=accrual.id, company_id=employee.company_id)
    return accrual


@router.get("/payments", response_model=list[PayrollPaymentOut], dependencies=[Depends(require_module("finance"))])
def list_payments(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids_with_role(db, user, company_id, PAYROLL_EDITORS)
    return (
        db.query(PayrollPayment)
        .filter(PayrollPayment.company_id.in_(company_ids))
        .order_by(PayrollPayment.date.desc())
        .all()
    )


@router.post("/payments", response_model=PayrollPaymentOut, dependencies=[Depends(require_module("finance"))])
def create_payment(
    payload: PayrollPaymentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    employee = _get_or_404(db, user, Employee, payload.employee_id, "Сотрудник не найден")
    check_company_role(db, user, employee.company_id, PAYROLL_EDITORS)
    if payload.accrual_id:
        accrual = _get_or_404(db, user, PayrollAccrual, payload.accrual_id, "Начисление не найдено")
        if accrual.company_id != employee.company_id:
            raise HTTPException(status_code=400, detail="Начисление принадлежит другой компании")
    get_or_404_accessible(db, Account, payload.account_id, [employee.company_id], "Счёт не найден")

    payment = PayrollPayment(**payload.model_dump(), company_id=employee.company_id)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    log_action(db, user, action="create", entity_type="payroll_payment", entity_id=payment.id, company_id=employee.company_id)
    return payment


@router.get("/summary-for-viewer", dependencies=[Depends(require_module("finance"))])
def payroll_summary_for_viewer(
    period: str | None = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Агрегированная сводка ФОТ без ФИО и реквизитов — доступна viewer
    # (плюс admin/payroll_operator, которым и так открыты детальные эндпоинты).
    company_ids = resolve_company_ids_with_role(db, user, company_id, SUMMARY_VIEWERS)
    accrual_query = db.query(PayrollAccrual).filter(PayrollAccrual.company_id.in_(company_ids))
    payment_query = db.query(PayrollPayment).filter(PayrollPayment.company_id.in_(company_ids))

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
