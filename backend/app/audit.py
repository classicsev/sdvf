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
) -> None:
    db.add(
        AuditLog(
            company_id=user.company_id,
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=details,
        )
    )
    db.commit()
