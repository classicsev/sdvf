from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import generate_api_key, get_current_user, require_roles
from app.database import get_db
from app.models import ApiKey, RoleEnum, User
from app.schemas import ApiKeyCreated, ApiKeyCreateIn, ApiKeyOut
from app.utils import get_or_404

router = APIRouter(
    prefix="/api-keys", tags=["api-keys"], dependencies=[Depends(require_roles([RoleEnum.admin]))]
)


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(ApiKey)
        .filter(ApiKey.company_id == current_user.company_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@router.post("", response_model=ApiKeyCreated)
def create_api_key(
    payload: ApiKeyCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # company_id обязателен в get_or_404: без него admin компании A мог бы выпустить
    # ключ, аутентифицирующий как пользователь компании B, передав чужой user_id.
    target_user = get_or_404(
        db, User, payload.user_id or current_user.id, "Пользователь не найден", company_id=current_user.company_id
    )

    full_key, key_prefix, key_hash = generate_api_key()
    key = ApiKey(
        company_id=current_user.company_id,
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
    key = get_or_404(db, ApiKey, key_id, "Ключ не найден", company_id=current_user.company_id)
    db.delete(key)
    db.commit()
    log_action(db, current_user, "revoke_api_key", "api_key", key_id, {"name": key.name})
    return {"deleted": True}
