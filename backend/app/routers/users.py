from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    create_email_verification_token,
    decode_email_verification_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)
from app.database import get_db
from app.mailer import send_verification_email
from app.models import Company, RoleEnum, User
from app.schemas import CompanyRegisterIn, LoginRequest, TokenResponse, UserCreate, UserOut, UserUpdate
from app.utils import get_or_404

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


def _get_user_or_404(db: Session, user_id: str, company_id: str) -> User:
    return get_or_404(db, User, user_id, "Пользователь не найден", company_id=company_id)


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    # hashed_password может быть NULL у пользователей, заведённых через OAuth
    # (VK ID и т.п.) — им обычный вход по паролю недоступен, только через провайдера.
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Учётная запись деактивирована")
    token = create_access_token({"sub": user.id, "role": user.role.value})
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@auth_router.post("/register-company", response_model=TokenResponse)
def register_company(payload: CompanyRegisterIn, db: Session = Depends(get_db)):
    # Проверено на бэкенде, а не только визуально на фронте — 152-ФЗ требует
    # реального согласия, не просто скрытого чекбокса в форме.
    if not payload.pdn_consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо согласие на обработку персональных данных",
        )
    # email уникален глобально (не в рамках компании) — см. models.py:User
    if db.query(User).filter(User.email == payload.admin_email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email уже занят")

    # Минимальный доступ по умолчанию (см. README) — только Учёт; Склад компания
    # включает себе сама в кабинете, когда понадобится (страница "Модули").
    company = Company(name=payload.company_name, module_finance_enabled=True, module_warehouse_enabled=False)
    db.add(company)
    db.flush()

    admin = User(
        company_id=company.id,
        email=payload.admin_email,
        full_name=payload.admin_full_name,
        hashed_password=hash_password(payload.admin_password),
        phone=payload.admin_phone,
        role=RoleEnum.admin,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    # Не блокирует регистрацию при сбое отправки (см. app/mailer.py) — аккаунт
    # уже создан и активен, письмо можно будет запросить повторно.
    send_verification_email(admin.email, create_email_verification_token(admin.id))

    token = create_access_token({"sub": admin.id, "role": admin.role.value})
    return TokenResponse(access_token=token)


@auth_router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user_id = decode_email_verification_token(token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ссылка недействительна или устарела")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ссылка недействительна или устарела")
    user.email_verified = True
    db.commit()
    return {"verified": True}


@auth_router.post("/resend-verification")
def resend_verification(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.email_verified:
        return {"sent": False, "reason": "already_verified"}
    if not user.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="К аккаунту не привязан email")
    sent = send_verification_email(user.email, create_email_verification_token(user.id))
    return {"sent": sent}


@users_router.get("", response_model=list[UserOut], dependencies=[Depends(require_roles([RoleEnum.admin]))])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(User).filter(User.company_id == current_user.company_id).all()


@users_router.post("", response_model=UserOut, dependencies=[Depends(require_roles([RoleEnum.admin]))])
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # email уникален глобально (не в рамках компании) — см. models.py:User
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email уже занят")

    user = User(
        company_id=current_user.company_id,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        project_id=payload.project_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@users_router.patch("/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles([RoleEnum.admin]))])
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = _get_user_or_404(db, user_id, current_user.company_id)
    changes = payload.model_dump(exclude_unset=True)

    if target.id == current_user.id:
        if "role" in changes and changes["role"] != current_user.role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя изменить свою роль")
        if changes.get("is_active") is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя деактивировать самого себя")

    password = changes.pop("password", None)
    if password:
        target.hashed_password = hash_password(password)

    for field, value in changes.items():
        setattr(target, field, value)

    db.commit()
    db.refresh(target)
    return target


@users_router.delete("/{user_id}", dependencies=[Depends(require_roles([RoleEnum.admin]))])
def delete_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    target = _get_user_or_404(db, user_id, current_user.company_id)
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить самого себя")

    # Физическое удаление заблокировано FK (transactions.created_by, audit_log.user_id,
    # automation_rules.created_by) — деактивируем вместо удаления, доступ пользователя
    # блокируется через is_active в get_current_user.
    target.is_active = False
    db.commit()
    return {"deleted": True}
