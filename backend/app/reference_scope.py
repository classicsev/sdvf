import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Category, CategoryCompany, Project, ProjectCompany

# Статья/проект видны компании X, если она владеющая (model.company_id), ИЛИ
# запись глобальная (is_global — динамически видна во всех компаниях холдинга,
# включая будущие), ИЛИ X явно указана в *_companies (см. models.py). Общая
# логика для обоих справочников — используется и в списках (reference.py), и
# при валидации category_id/project_id на самой операции (transactions.py).


def apply_visibility_filter(db: Session, query, model, company_ids: list[str]):
    assoc_model = CategoryCompany if model is Category else ProjectCompany
    fk_col = assoc_model.category_id if model is Category else assoc_model.project_id
    visible_ids_select = select(fk_col).where(assoc_model.company_id.in_(company_ids))
    return query.filter(
        or_(
            model.company_id.in_(company_ids),
            model.is_global.is_(True),
            model.id.in_(visible_ids_select),
        )
    )


def get_visible_or_404(db: Session, model, entity_id: str, company_ids: list[str], detail: str = "Запись не найдена"):
    try:
        uuid.UUID(str(entity_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    obj = apply_visibility_filter(db, db.query(model).filter(model.id == entity_id), model, company_ids).first()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return obj
