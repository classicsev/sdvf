from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)
from app.database import get_db
from app.models import RoleEnum, User
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserOut, UserUpdate
from app.utils import get_or_404

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


def _get_user_or_404(db: Session, user_id: str) -> User:
    return get_or_404(db, User, user_id, "Пользователь не найден")


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Учётная запись деактивирована")
    token = create_access_token({"sub": user.id, "role": user.role.value})
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@users_router.get("", response_model=list[UserOut], dependencies=[Depends(require_roles([RoleEnum.admin]))])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()


@users_router.post("", response_model=UserOut, dependencies=[Depends(require_roles([RoleEnum.admin]))])
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email уже занят")

    user = User(
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
    target = _get_user_or_404(db, user_id)
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
    target = _get_user_or_404(db, user_id)
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить самого себя")

    # Физическое удаление заблокировано FK (transactions.created_by, audit_log.user_id,
    # automation_rules.created_by) — деактивируем вместо удаления, доступ пользователя
    # блокируется через is_active в get_current_user.
    target.is_active = False
    db.commit()
    return {"deleted": True}
