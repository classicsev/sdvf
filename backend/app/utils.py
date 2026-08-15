import uuid
from typing import Type, TypeVar

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)


def delete_or_deactivate(db: Session, obj: ModelT, references: list[tuple[Type, str]]) -> bool:
    """Удаляет obj физически, если на него нигде нет ссылок; иначе деактивирует
    (is_active=False), чтобы не упасть в FK-констрейнт и не оборвать историю операций.
    references — список (Модель, поле_внешнего_ключа) для проверки использования.
    Возвращает True при физическом удалении, False при деактивации."""
    for model, fk_field in references:
        if db.query(model).filter(getattr(model, fk_field) == obj.id).first() is not None:
            obj.is_active = False
            db.commit()
            return False
    db.delete(obj)
    db.commit()
    return True


def move_to_company(
    db: Session, obj: ModelT, target_company_id: str, references: list[tuple[Type, str]]
) -> None:
    """Переносит справочную запись в другую компанию — только если на неё
    нигде нет ссылок (тот же список references, что и у delete_or_deactivate):
    у операции/начисления/заказа и т.п. свой собственный company_id, и перенос
    только самой записи оставил бы их рассинхронизированными с её новой
    компанией. Пустая (ещё неиспользуемая) запись переносится свободно."""
    for model, fk_field in references:
        if db.query(model).filter(getattr(model, fk_field) == obj.id).first() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Запись уже используется — перенести в другую компанию нельзя, пока есть связанные данные",
            )
    obj.company_id = target_company_id
    db.commit()


def get_or_404(
    db: Session,
    model: Type[ModelT],
    entity_id: str,
    detail: str = "Запись не найдена",
    company_id: str | None = None,
) -> ModelT:
    # id приходит от клиента как произвольная строка; без проверки формата
    # невалидный UUID уронит запрос в БД с 500 вместо честного 404.
    try:
        uuid.UUID(str(entity_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    # company_id — обязательная защита от межтенантного доступа (IDOR): без неё
    # пользователь одной компании, зная/подобрав UUID чужой записи, мог бы прочитать
    # или изменить данные другой компании через db.get() по одному только PK.
    if company_id is not None:
        obj = db.query(model).filter(model.id == entity_id, model.company_id == company_id).first()
    else:
        obj = db.get(model, entity_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return obj


def get_or_404_accessible(
    db: Session,
    model: Type[ModelT],
    entity_id: str,
    accessible_company_ids: list[str],
    detail: str = "Запись не найдена",
) -> ModelT:
    """Как get_or_404, но company_id проверяется против СПИСКА доступных
    компаний (см. auth.get_accessible_company_ids), а не одной — для
    роутеров, переведённых на мульти-компании (план "Мульти-компании")."""
    try:
        uuid.UUID(str(entity_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    obj = db.query(model).filter(model.id == entity_id, model.company_id.in_(accessible_company_ids)).first()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return obj
