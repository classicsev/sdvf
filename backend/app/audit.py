from typing import Optional

from fastapi.encoders import jsonable_encoder
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
    #
    # jsonable_encoder — details нередко приходит "как есть" из
    # payload.model_dump(exclude_unset=True) (см. transactions.py::update_transaction),
    # где поля вроде date_odds/amount остаются объектами date/Decimal, а не
    # JSON-примитивами — драйвер JSONB падает на них с "Object of type date is
    # not JSON serializable" (реальный сбой на проде при простом сохранении
    # операции). Приводим details к JSON-безопасному виду здесь же, один раз
    # для всех вызовов, а не в каждом отдельном роутере по месту.
    db.add(
        AuditLog(
            company_id=company_id,
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=jsonable_encoder(details) if details is not None else None,
        )
    )
    db.commit()
