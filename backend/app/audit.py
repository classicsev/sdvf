from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def log_action(
    db: Session,
    user: User,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    *,
    company_id: str,
) -> None:
    # company_id — компания, где ФАКТИЧЕСКИ произошло действие (не обязательно
    # "первая"/primary компания пользователя — см. план "Мульти-компании").
    # Раньше бралась из user.company_id и все записи аудита ошибочно
    # приписывались первой компании пользователя, даже для действий в других
    # его компаниях — это ломало и сам аудит-лог, и видимость по ролям.
    db.add(
        AuditLog(
            company_id=company_id,
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=details,
        )
    )
    db.commit()
