import uuid

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Category, CategoryCompany, Project, ProjectCompany, ProjectGroup, ProjectGroupCompany

# Статья/проект/группа проектов видны компании X, если она владеющая
# (model.company_id), ИЛИ запись глобальная (is_global — динамически видна во
# всех компаниях холдинга, включая будущие), ИЛИ X явно указана в
# *_companies (см. models.py). Общая логика для всех трёх справочников —
# используется и в списках (reference.py), и при валидации
# category_id/project_id на самой операции (transactions.py).

_ASSOC_BY_MODEL = {
    Category: (CategoryCompany, "category_id"),
    Project: (ProjectCompany, "project_id"),
    ProjectGroup: (ProjectGroupCompany, "project_group_id"),
}


def _assoc_for(model):
    assoc_model, fk_name = _ASSOC_BY_MODEL[model]
    return assoc_model, getattr(assoc_model, fk_name)


def apply_visibility_filter(db: Session, query, model, company_ids: list[str], mode: str = "union"):
    """mode="union" (по умолчанию) — запись видна хотя бы в одной из company_ids
    (обычное поведение). mode="intersection" имеет смысл только при нескольких
    company_ids — запись видна ВО ВСЕХ них одновременно (реально расшарена
    между именно этими компаниями, а не просто попадает в общий список видимых
    отовсюду). При одной компании оба режима эквивалентны union."""
    assoc_model, fk_col = _assoc_for(model)

    if mode == "intersection" and len(company_ids) > 1:
        conditions = []
        for cid in company_ids:
            visible_for_cid = select(fk_col).where(assoc_model.company_id == cid)
            conditions.append(
                or_(model.company_id == cid, model.is_global.is_(True), model.id.in_(visible_for_cid))
            )
        return query.filter(and_(*conditions))

    visible_ids_select = select(fk_col).where(assoc_model.company_id.in_(company_ids))
    return query.filter(
        or_(
            model.company_id.in_(company_ids),
            model.is_global.is_(True),
            model.id.in_(visible_ids_select),
        )
    )


def apply_own_only_filter(query, model, company_ids: list[str]):
    """"Только свои — без расшаренных": в отличие от простого company_id.in_
    (который включил бы и глобальные/расшаренные записи, раз они формально
    ПРИНАДЛЕЖАТ одной из company_ids), тут исключается любая запись, чья
    видимость выходит ЗА пределы company_ids — is_global (видна вообще
    везде, включая будущие компании) или visible_company_ids с компанией не
    из этого набора. Цель — показать записи, эксклюзивные именно для
    выбранных компаний, а не просто заведённые в одной из них."""
    assoc_model, fk_col = _assoc_for(model)
    leaks_outside_filter = select(fk_col).where(assoc_model.company_id.notin_(company_ids))
    return query.filter(
        model.company_id.in_(company_ids),
        model.is_global.is_(False),
        ~model.id.in_(leaks_outside_filter),
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
