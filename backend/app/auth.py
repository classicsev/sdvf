import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Iterable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import ApiKey, Company, RoleEnum, User

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
    """Row-level security helper — используется роутерами, ещё не переведёнными
    на мульти-компании (см. план "Мульти-компании"). Возвращает company_id
    "первой" (по дате создания) компании пользователя через User.company_id —
    свойство-заглушку на модели, а не колонку. Новый код должен использовать
    get_accessible_company_ids/check_company_role."""
    return user.company_id


def get_accessible_company_ids(db: Session, user: User) -> list[str]:
    """Все компании, к которым у пользователя есть доступ (через
    company_members) — в отличие от scope_company_filter не одна, а список.
    Используется списочными эндпоинтами, которые должны показывать данные
    сразу по всем компаниям пользователя без переключения контекста."""
    from app.models import CompanyMember

    return [
        row.company_id
        for row in db.query(CompanyMember.company_id).filter(CompanyMember.user_id == user.id).all()
    ]


def get_company_role(db: Session, user: User, company_id: str) -> Optional[RoleEnum]:
    """Роль пользователя в конкретной компании, или None, если доступа нет вовсе."""
    from app.models import CompanyMember

    try:
        uuid.UUID(str(company_id))
    except (ValueError, AttributeError):
        return None
    row = (
        db.query(CompanyMember)
        .filter(CompanyMember.user_id == user.id, CompanyMember.company_id == company_id)
        .first()
    )
    return row.role if row else None


def check_company_role(db: Session, user: User, company_id: str, allowed: Iterable[RoleEnum]) -> RoleEnum:
    """Поднимает 403/404, если у пользователя нет одной из допустимых ролей
    именно в этой компании. Не Depends-фабрика (в отличие от require_roles) —
    company_id обычно приходит из path/body конкретного эндпоинта, а не
    доступен на этапе объявления зависимостей."""
    role = get_company_role(db, user, company_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Компания не найдена")
    if role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для этого действия в этой компании",
        )
    return role


def resolve_company_ids(db: Session, user: User, company_id: Optional[str]) -> list[str]:
    """Для списочных/отчётных эндпоинтов (см. план "Мульти-компании"): без
    ?company_id= — все доступные компании (сводно, без переключения контекста);
    с ?company_id= — сужение до одной, если у пользователя есть к ней доступ
    (иначе 404, а не пустой список — не подсказываем, какие company_id валидны)."""
    accessible = get_accessible_company_ids(db, user)
    if company_id is None:
        return accessible
    if company_id not in accessible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Компания не найдена")
    return [company_id]


def resolve_company_ids_with_role(
    db: Session, user: User, company_id: Optional[str], allowed: Iterable[RoleEnum]
) -> list[str]:
    """Как resolve_company_ids, но только компании, где роль пользователя
    входит в allowed — для чувствительных данных (зарплата и т.п.), где
    "есть доступ к компании вообще" недостаточно: payroll_operator в одной
    компании не должен видеть детальные записи ФОТ компании, где он viewer."""
    from app.models import CompanyMember

    query = db.query(CompanyMember.company_id).filter(
        CompanyMember.user_id == user.id, CompanyMember.role.in_(list(allowed))
    )
    if company_id is not None:
        query = query.filter(CompanyMember.company_id == company_id)
    ids = [row.company_id for row in query.all()]
    if not ids:
        if company_id is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Компания не найдена")
        # Ни в одной компании нет нужной роли — это не "пусто", а "нет доступа
        # вовсе" (как раньше — единый require_roles на весь эндпоинт).
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для этого действия"
        )
    return ids


def resolve_write_company_id(
    db: Session, user: User, company_id: Optional[str], allowed: Iterable[RoleEnum]
) -> str:
    """Для создания записей: явный company_id (пользователь выбрал компанию —
    проверяем роль в ней) или, если не передан, "первая" компания пользователя
    (обратная совместимость с формами, ещё не умеющими выбирать компанию)."""
    target = company_id or user.company_id
    check_company_role(db, user, target, allowed)
    return target


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


SSO_LINK_CONFIRM_PURPOSE = "sso_link_confirm"
SSO_LINK_CONFIRM_EXPIRE_MINUTES = 30


def create_sso_link_confirm_token(user_id: str, redirect_uri: str, state: str) -> str:
    """Привязка аккаунта к внешнему сервису (СДВФ) — действие чувствительнее
    обычного SSO-входа: простого клика в уже открытой сессии недостаточно
    (сессия может быть чужой/старой на том же браузере), нужно реальное
    подтверждение владения почтой. redirect_uri/state едут внутри подписанного
    токена, а не через отдельное хранилище состояния — секрет не даёт их подменить."""
    expire = datetime.utcnow() + timedelta(minutes=SSO_LINK_CONFIRM_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "purpose": SSO_LINK_CONFIRM_PURPOSE,
        "redirect_uri": redirect_uri,
        "state": state,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_sso_link_confirm_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("purpose") != SSO_LINK_CONFIRM_PURPOSE:
        return None
    return payload


def require_module(*modules: str):
    """Dependency factory: 403, если ни один из перечисленных модулей не куплен
    ни в одной из доступных пользователю компаний. Несколько модулей — через ИЛИ
    (нужно для общих ресурсов вроде контрагентов, доступных и Учёту, и Складу).

    Usage: dependencies=[Depends(require_module("finance"))]
    """
    flag_by_module = {"finance": "module_finance_enabled", "warehouse": "module_warehouse_enabled"}

    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        accessible_ids = get_accessible_company_ids(db, user)
        if not accessible_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Этот модуль недоступен для вашей компании",
            )
        companies = db.query(Company).filter(Company.id.in_(accessible_ids)).all()
        if not any(getattr(company, flag_by_module[m]) for company in companies for m in modules):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Этот модуль недоступен для вашей компании",
            )
        return user

    return checker
