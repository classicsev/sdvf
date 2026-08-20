import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import check_company_role, get_current_user, hash_password, require_roles
from app.database import get_db
from app.models import Company, CompanyMember, RoleEnum, User
from app.schemas import (
    CompanyCreate,
    CompanyMemberCreate,
    CompanyMemberUpdate,
    CompanyMembershipOut,
    CompanyModulesIn,
    CompanyOut,
    CompanyUpdate,
)
from app.utils import get_or_404

router = APIRouter(prefix="/companies", tags=["companies"])

VALID_COMPANY_TYPES = {"legal_entity", "individual", "cn_legal_entity"}


def _find_membership_or_404(db: Session, user_id: str, company_id: str) -> CompanyMember:
    try:
        uuid.UUID(str(user_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник не найден")
    membership = (
        db.query(CompanyMember)
        .filter(CompanyMember.user_id == user_id, CompanyMember.company_id == company_id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник не найден")
    return membership


@router.get("/me", response_model=CompanyOut)
def get_my_company(user: User = Depends(get_current_user)):
    return user.company


@router.patch(
    "/me/modules",
    response_model=CompanyOut,
    dependencies=[Depends(require_roles([RoleEnum.admin]))],
)
def update_my_company_modules(
    payload: CompanyModulesIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    # Намеренно без require_module-гейта: компания, выключившая себе Учёт, должна
    # по-прежнему иметь возможность зайти сюда и включить его обратно.
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user.company, field, value)
    db.commit()
    db.refresh(user.company)
    return user.company


# --- Мульти-компании: любая компания пользователя, не только "первая" ---
# (см. план "Мульти-компании" — company_members заменяет одиночный
# User.company_id; эндпоинты выше остаются для обратной совместимости и
# продолжают работать с "первой" компанией пользователя).


@router.get("", response_model=list[CompanyMembershipOut])
def list_my_companies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(CompanyMember)
        .filter(CompanyMember.user_id == user.id)
        .order_by(CompanyMember.created_at)
        .all()
    )


@router.post("", response_model=CompanyMembershipOut, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.company_type not in VALID_COMPANY_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный тип компании")

    # У личного счёта физлица нет юр. реквизитов — минимальный тариф без Склада,
    # так же как при обычной регистрации (см. register_company в routers/users.py).
    company = Company(
        name=payload.name,
        company_type=payload.company_type,
        module_finance_enabled=True,
        module_warehouse_enabled=False,
        owner_user_id=user.id,
    )
    db.add(company)
    db.flush()

    membership = CompanyMember(user_id=user.id, company_id=company.id, role=RoleEnum.admin)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: str,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_company_role(db, user, company_id, [RoleEnum.admin])
    company = get_or_404(db, Company, company_id, "Компания не найдена")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("company_type") is not None and changes["company_type"] not in VALID_COMPANY_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный тип компании")
    for field, value in changes.items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company


@router.delete("/{company_id}")
def delete_company(
    company_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_company_role(db, user, company_id, [RoleEnum.admin])
    company = get_or_404(db, Company, company_id, "Компания не найдена")

    # Компанию можно удалить только "пустой" — как только в ней появляются
    # реальные данные (счета, операции, контрагенты и т.д.), FK на company_id
    # без ondelete=CASCADE у этих таблиц остановит удаление IntegrityError —
    # это и есть защита от случайной потери финансовых данных. Для компании
    # с историей — деактивация модулей, а не удаление.
    db.delete(company)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "В компании уже есть данные (счета, операции, контрагенты и т.п.) — "
                "удалить нельзя, чтобы не потерять историю. Отключите модули вместо удаления."
            ),
        )
    return {"deleted": True}


@router.patch("/{company_id}/modules", response_model=CompanyOut)
def update_company_modules(
    company_id: str,
    payload: CompanyModulesIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_company_role(db, user, company_id, [RoleEnum.admin])
    company = get_or_404(db, Company, company_id, "Компания не найдена")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company


@router.post("/{company_id}/members", response_model=CompanyMembershipOut, status_code=status.HTTP_201_CREATED)
def add_company_member(
    company_id: str,
    payload: CompanyMemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_company_role(db, user, company_id, [RoleEnum.admin])

    target = db.query(User).filter(User.email == payload.email).first()
    if target is None:
        if not payload.full_name or not payload.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователя с таким email ещё нет — укажите имя и пароль, чтобы создать аккаунт",
            )
        target = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
        )
        db.add(target)
        db.flush()
    else:
        existing = (
            db.query(CompanyMember)
            .filter(CompanyMember.user_id == target.id, CompanyMember.company_id == company_id)
            .first()
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="У пользователя уже есть доступ")

    membership = CompanyMember(
        user_id=target.id, company_id=company_id, role=payload.role, project_id=payload.project_id
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@router.patch("/{company_id}/members/{user_id}", response_model=CompanyMembershipOut)
def update_company_member(
    company_id: str,
    user_id: str,
    payload: CompanyMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_company_role(db, user, company_id, [RoleEnum.admin])
    membership = _find_membership_or_404(db, user_id, company_id)

    changes = payload.model_dump(exclude_unset=True)
    if "role" in changes and user_id == user.id and changes["role"] != membership.role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя изменить свою роль")
    for field, value in changes.items():
        setattr(membership, field, value)
    db.commit()
    db.refresh(membership)
    return membership


@router.delete("/{company_id}/members/{user_id}")
def remove_company_member(
    company_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_company_role(db, user, company_id, [RoleEnum.admin])
    membership = _find_membership_or_404(db, user_id, company_id)

    # Не даём компании остаться без единого admin — ни себя, ни кого-либо ещё
    # убрать, если это последний admin.
    if membership.role == RoleEnum.admin:
        other_admins = (
            db.query(CompanyMember)
            .filter(
                CompanyMember.company_id == company_id,
                CompanyMember.role == RoleEnum.admin,
                CompanyMember.user_id != user_id,
            )
            .count()
        )
        if other_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя убрать последнего администратора компании",
            )

    db.delete(membership)
    db.commit()
    return {"removed": True}
