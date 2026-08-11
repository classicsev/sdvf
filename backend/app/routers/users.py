import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    create_email_verification_token,
    decode_email_verification_token,
    get_current_user,
    hash_password,
    resolve_company_ids_with_role,
    resolve_write_company_id,
    verify_password,
)
from app.database import get_db
from app.mailer import send_verification_email
from app.models import Company, CompanyMember, RoleEnum, User
from app.schemas import (
    CompanyRegisterIn,
    LoginRequest,
    MyProfileUpdate,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])

AVATAR_DIR = Path(__file__).resolve().parent.parent.parent / "media" / "avatars"
MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_AVATAR_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
AVATAR_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


ADMIN_ONLY = [RoleEnum.admin]


def _get_company_member_or_404(db: Session, user_id: str, company_id: str) -> tuple[User, CompanyMember]:
    """Пользователь + его членство в company_id — 404, если пользователя нет
    вовсе или он не состоит в этой компании (не палим существование чужого
    аккаунта, как и раньше делал get_or_404 по company_id)."""
    try:
        uuid.UUID(str(user_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    membership = (
        db.query(CompanyMember)
        .filter(CompanyMember.user_id == user_id, CompanyMember.company_id == company_id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    target = db.get(User, user_id)
    return target, membership


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    # hashed_password может быть NULL у пользователей, заведённых через OAuth
    # (VK ID и т.п.) — им обычный вход по паролю недоступен, только через провайдера.
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Учётная запись деактивирована")
    # Роль больше не кладём в токен — она теперь per-company (см. company_members),
    # а не единая для пользователя. Эндпоинты проверяют роль под нужную компанию сами.
    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@auth_router.patch("/me/profile", response_model=UserOut)
def update_my_profile(
    payload: MyProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.gender is not None and payload.gender not in ("", "M", "F"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректное значение пола")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@auth_router.post("/me/avatar", response_model=UserOut)
def upload_my_avatar(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Фото должно быть в формате JPEG, PNG, WEBP или GIF",
        )

    contents = file.file.read()
    if len(contents) > MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Фото слишком большое — максимум 5 МБ")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    ext = AVATAR_EXT_BY_CONTENT_TYPE[file.content_type]
    filename = f"{uuid.uuid4()}{ext}"
    (AVATAR_DIR / filename).write_bytes(contents)

    user.avatar_url = f"/media/avatars/{filename}"
    db.commit()
    db.refresh(user)
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
        email=payload.admin_email,
        full_name=payload.admin_full_name,
        hashed_password=hash_password(payload.admin_password),
        phone=payload.admin_phone,
    )
    db.add(admin)
    db.flush()

    db.add(CompanyMember(user_id=admin.id, company_id=company.id, role=RoleEnum.admin))
    company.owner_user_id = admin.id
    db.commit()
    db.refresh(admin)

    # Не блокирует регистрацию при сбое отправки (см. app/mailer.py) — аккаунт
    # уже создан и активен, письмо можно будет запросить повторно.
    send_verification_email(admin.email, create_email_verification_token(admin.id))

    token = create_access_token({"sub": admin.id})
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


@users_router.get("", response_model=list[UserOut])
def list_users(
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Пользователи КОНКРЕТНОЙ компании (по умолчанию — всех, где current_user
    # admin), не только "первой" — см. план "Мульти-компании". Полноценное
    # управление ролью/проектом в одной компании — тоже здесь; отзыв доступа
    # к одной компании (без затрагивания остальных) — через
    # DELETE /companies/{id}/members (routers/companies.py).
    company_ids = resolve_company_ids_with_role(db, current_user, company_id, ADMIN_ONLY)
    user_ids = db.query(CompanyMember.user_id).filter(CompanyMember.company_id.in_(company_ids)).scalar_subquery()
    return db.query(User).filter(User.id.in_(user_ids)).all()


@users_router.post("", response_model=UserOut)
def create_user(
    payload: UserCreate,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_company_id = resolve_write_company_id(db, current_user, company_id, ADMIN_ONLY)

    # email уникален глобально (не в рамках компании) — см. models.py:User
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email уже занят")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(
        CompanyMember(
            user_id=user.id,
            company_id=target_company_id,
            role=payload.role,
            project_id=payload.project_id,
        )
    )
    db.commit()
    db.refresh(user)
    return user


@users_router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_company_id = resolve_write_company_id(db, current_user, company_id, ADMIN_ONLY)
    target, membership = _get_company_member_or_404(db, user_id, target_company_id)
    changes = payload.model_dump(exclude_unset=True)

    if target.id == current_user.id:
        # Сравниваем с ролью в РЕДАКТИРУЕМОЙ компании, а не с "первой" —
        # пользователь может быть admin в одной своей компании и viewer в другой.
        if "role" in changes and changes["role"] != membership.role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя изменить свою роль")
        if changes.get("is_active") is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя деактивировать самого себя")

    password = changes.pop("password", None)
    if password:
        target.hashed_password = hash_password(password)

    if "role" in changes:
        membership.role = changes.pop("role")
    if "project_id" in changes:
        membership.project_id = changes.pop("project_id")

    for field, value in changes.items():
        setattr(target, field, value)

    db.commit()
    db.refresh(target)
    return target


@users_router.delete("/{user_id}")
def delete_user(
    user_id: str,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_company_id = resolve_write_company_id(db, current_user, company_id, ADMIN_ONLY)
    target, _membership = _get_company_member_or_404(db, user_id, target_company_id)
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить самого себя")

    # Физическое удаление заблокировано FK (transactions.created_by, audit_log.user_id,
    # automation_rules.created_by) — деактивируем вместо удаления, доступ пользователя
    # блокируется через is_active в get_current_user. Деактивация глобальна (весь
    # аккаунт), а не только доступ к этой компании — для отзыва доступа к ОДНОЙ
    # компании без затрагивания остальных используйте DELETE /companies/{id}/members.
    target.is_active = False
    db.commit()
    return {"deleted": True}
