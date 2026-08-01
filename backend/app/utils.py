import uuid
from typing import Type, TypeVar

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)


def get_or_404(db: Session, model: Type[ModelT], entity_id: str, detail: str = "Запись не найдена") -> ModelT:
    # id приходит от клиента как произвольная строка; без проверки формата
    # невалидный UUID уронит запрос в БД с 500 вместо честного 404.
    try:
        uuid.UUID(str(entity_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    obj = db.get(model, entity_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return obj
