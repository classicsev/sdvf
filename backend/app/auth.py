import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Iterable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import ApiKey, RoleEnum, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

API_KEY_PREFIX = "fp_"


def generate_api_key() -> tuple[str, str, str]:
    """Возвращает (полный ключ — показать один раз, префикс для списка, hash для хранения)."""
    full_key = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    return full_key, full_key[:10], hash_api_key(full_key)


def hash_api_key(raw_key: str) -> str:
    # SHA-256, а не bcrypt: ключ ищется по значению (нужен быстрый детерминированный lookup),
    # а не проверяется против одного известного пользователя — энтропии token_urlsafe(32) достаточно
    return hashlib.sha256(raw_key.encode()).hexdigest()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


EMAIL_VERIFICATION_PURPOSE = "verify_email"
EMAIL_VERIFICATION_EXPIRE_HOURS = 24


def create_email_verification_token(user_id: str) -> str:
    """Отдельный JWT (не access-токен для API) — только для ссылки в письме
    подтверждения. `purpose` защищает от подмены: обычный access-токен нельзя
    подсунуть в /auth/verify-email, и наоборот."""
    expire = datetime.utcnow() + timedelta(hours=EMAIL_VERIFICATION_EXPIRE_HOURS)
    payload = {"sub": user_id, "purpose": EMAIL_VERIFICATION_PURPOSE, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_email_verification_token(token: str) -> Optional[str]:
    """Возвращает user_id, если токен валиден и не истёк, иначе None
    (истёкшая/подделанная/чужого purpose ссылка — не 500, а понятный отказ)."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("purpose") != EMAIL_VERIFICATION_PURPOSE:
        return None
    return payload.get("sub")


OAUTH_STATE_PURPOSE = "oauth_state"
OAUTH_STATE_EXPIRE_MINUTES = 10


def create_oauth_state_token(provider: str, code_verifier: Optional[str] = None) -> str:
    """Подписанный `state` для OAuth-редиректа. Провайдер возвращает state как есть —
    подпись не даёт его подделать, а code_verifier (нужен только VK ID, PKCE) едет
    внутри вместо серверной сессии, которой у нас нет."""
    expire = datetime.utcnow() + timedelta(minutes=OAUTH_STATE_EXPIRE_MINUTES)
    payload = {
        "purpose": OAUTH_STATE_PURPOSE,
        "provider": provider,
        "code_verifier": code_verifier,
        "nonce": secrets.token_urlsafe(8),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_oauth_state_token(token: str, expected_provider: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("purpose") != OAUTH_STATE_PURPOSE or payload.get("provider") != expected_provider:
        return None
    return payload


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Depends(api_key_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось подтвердить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if api_key is not None:
        key_row = db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(api_key)).first()
        if key_row is None or not key_row.is_active:
            raise credentials_exception
        user = db.get(User, key_row.user_id)
        if user is None or not user.is_active:
            raise credentials_exception
        key_row.last_used_at = datetime.utcnow()
        db.commit()
        return user

    if token is None:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(allowed: Iterable[RoleEnum]):
    """Dependency factory: restrict an endpoint to a set of roles.

    Usage: @router.post(..., dependencies=[Depends(require_roles([RoleEnum.admin]))])
    """

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для этого действия",
            )
        return user

    return checker


def scope_project_filter(user: User) -> str | None:
    """Row-level security helper.

    Возвращает project_id, к которому нужно принудительно ограничить запрос,
    если у пользователя роль project_manager. Иначе None (без ограничения).
    ВАЖНО: фильтр всегда берётся из токена пользователя, а не из query-параметра
    запроса — иначе project_manager сможет подменить ?project= и увидеть чужой проект.
    """
    if user.role == RoleEnum.project_manager:
        return user.project_id
    return None


def scope_company_filter(user: User) -> str:
    """Row-level security helper — мультитенантность.

    В отличие от scope_project_filter не Optional: у пользователя всегда ровно
    одна компания. Возвращаемое значение всегда берётся из user (из БД по токену),
    никогда из query-параметра запроса — та же логика, что и у scope_project_filter.
    """
    return user.company_id


SSO_IDENTITY_CODE_PURPOSE = "sso_identity_code"
SSO_IDENTITY_CODE_EXPIRE_SECONDS = 60


def create_sso_identity_code(user_id: str) -> str:
    """Аналог authorization code в OAuth2, но без отдельной таблицы — короткоживущий
    (60 сек) подписанный JWT с purpose-claim, тот же паттерн, что и у
    create_oauth_state_token/create_email_verification_token. Используется, когда
    Учёт выступает identity-провайдером для СДВФ (routers/identity_provider.py)."""
    expire = datetime.utcnow() + timedelta(seconds=SSO_IDENTITY_CODE_EXPIRE_SECONDS)
    payload = {"sub": user_id, "purpose": SSO_IDENTITY_CODE_PURPOSE, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_sso_identity_code(code: str) -> Optional[str]:
    try:
        payload = jwt.decode(code, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("purpose") != SSO_IDENTITY_CODE_PURPOSE:
        return None
    return payload.get("sub")


def require_module(*modules: str):
    """Dependency factory: 403, если ни один из перечисленных модулей не куплен
    компанией пользователя. Несколько модулей — через ИЛИ (нужно для общих
    ресурсов вроде контрагентов, доступных и Учёту, и Складу).

    Usage: dependencies=[Depends(require_module("finance"))]
    """
    flag_by_module = {"finance": "module_finance_enabled", "warehouse": "module_warehouse_enabled"}

    def checker(user: User = Depends(get_current_user)) -> User:
        if not any(getattr(user.company, flag_by_module[m]) for m in modules):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Этот модуль недоступен для вашей компании",
            )
        return user

    return checker
