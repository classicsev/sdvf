import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import (
    check_company_role,
    generate_api_key,
    get_accessible_company_ids,
    get_current_user,
    resolve_company_ids_with_role,
    resolve_write_company_id,
)
from app.database import get_db
from app.models import ApiKey, CompanyMember, RoleEnum, User
from app.schemas import ApiKeyCreated, ApiKeyCreateIn, ApiKeyOut
from app.utils import get_or_404_accessible

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

ADMIN_ONLY = [RoleEnum.admin]


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids_with_role(db, current_user, company_id, ADMIN_ONLY)
    return (
        db.query(ApiKey)
        .filter(ApiKey.company_id.in_(company_ids))
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@router.post("", response_model=ApiKeyCreated)
def create_api_key(
    payload: ApiKeyCreateIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_company_id = resolve_write_company_id(db, current_user, company_id, ADMIN_ONLY)

    # Membership в target_company_id обязателен: без него admin компании A мог бы
    # выпустить ключ, аутентифицирующий как пользователь компании B, передав чужой user_id.
    target_user_id = payload.user_id or current_user.id
    try:
        uuid.UUID(str(target_user_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    is_member = (
        db.query(CompanyMember)
        .filter(CompanyMember.user_id == target_user_id, CompanyMember.company_id == target_company_id)
        .first()
        is not None
    )
    if not is_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    target_user = db.get(User, target_user_id)

    full_key, key_prefix, key_hash = generate_api_key()
    key = ApiKey(
        company_id=target_company_id,
        name=payload.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        user_id=target_user.id,
        created_by=current_user.id,
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    log_action(
        db, current_user, "create_api_key", "api_key", key.id,
        {"name": key.name, "user_id": target_user.id},
    )

    return ApiKeyCreated(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        user_id=key.user_id,
        is_active=key.is_active,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        key=full_key,
    )


@router.delete("/{key_id}")
def revoke_api_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    key = get_or_404_accessible(
        db, ApiKey, key_id, get_accessible_company_ids(db, current_user), "Ключ не найден"
    )
    check_company_role(db, current_user, key.company_id, ADMIN_ONLY)
    db.delete(key)
    db.commit()
    log_action(db, current_user, "revoke_api_key", "api_key", key_id, {"name": key.name})
    return {"deleted": True}
