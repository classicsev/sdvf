from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import Account, Category, Counterparty, Project, RoleEnum
from app.schemas import (
    AccountIn,
    AccountOut,
    CategoryIn,
    CategoryOut,
    CounterpartyIn,
    CounterpartyOut,
    ProjectIn,
    ProjectOut,
)
from app.utils import get_or_404

router = APIRouter(tags=["reference"])

ADMIN_ONLY = [RoleEnum.admin]


def _get_or_404(db: Session, model, entity_id: str):
    return get_or_404(db, model, entity_id)


# ---------------------------------------------------------------------------
# Статьи (категории)
# ---------------------------------------------------------------------------


@router.get("/categories", response_model=list[CategoryOut], dependencies=[Depends(get_current_user)])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()


@router.post("/categories", response_model=CategoryOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def create_category(payload: CategoryIn, db: Session = Depends(get_db)):
    obj = Category(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/categories/{category_id}", response_model=CategoryOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def update_category(category_id: str, payload: CategoryIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, Category, category_id)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/categories/{category_id}", dependencies=[Depends(require_roles(ADMIN_ONLY))])
def delete_category(category_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, Category, category_id)
    db.delete(obj)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Проекты
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut], dependencies=[Depends(get_current_user)])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()


@router.post("/projects", response_model=ProjectOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def create_project(payload: ProjectIn, db: Session = Depends(get_db)):
    obj = Project(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/projects/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def update_project(project_id: str, payload: ProjectIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, Project, project_id)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/projects/{project_id}", dependencies=[Depends(require_roles(ADMIN_ONLY))])
def delete_project(project_id: str, db: Session = Depends(get_db)):
    # TODO: решить бизнес-правило — запрещать удаление, если на проект уже есть
    # ссылки в transactions/payroll, либо мягко деактивировать (is_active=False)
    # вместо физического удаления
    obj = _get_or_404(db, Project, project_id)
    db.delete(obj)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Счета
# ---------------------------------------------------------------------------


@router.get("/accounts", response_model=list[AccountOut], dependencies=[Depends(get_current_user)])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(Account).all()


@router.post("/accounts", response_model=AccountOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def create_account(payload: AccountIn, db: Session = Depends(get_db)):
    obj = Account(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/accounts/{account_id}", response_model=AccountOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def update_account(account_id: str, payload: AccountIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, Account, account_id)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/accounts/{account_id}", dependencies=[Depends(require_roles(ADMIN_ONLY))])
def delete_account(account_id: str, db: Session = Depends(get_db)):
    # TODO: запретить удаление счёта, если по нему уже есть проведённые transactions —
    # в этом случае предложить деактивировать (is_active=False), а не удалять физически
    obj = _get_or_404(db, Account, account_id)
    db.delete(obj)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Контрагенты
# ---------------------------------------------------------------------------


@router.get("/counterparties", response_model=list[CounterpartyOut], dependencies=[Depends(get_current_user)])
def list_counterparties(db: Session = Depends(get_db)):
    return db.query(Counterparty).all()


@router.post("/counterparties", response_model=CounterpartyOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def create_counterparty(payload: CounterpartyIn, db: Session = Depends(get_db)):
    obj = Counterparty(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/counterparties/{counterparty_id}",
    response_model=CounterpartyOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY))],
)
def update_counterparty(counterparty_id: str, payload: CounterpartyIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, Counterparty, counterparty_id)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/counterparties/{counterparty_id}", dependencies=[Depends(require_roles(ADMIN_ONLY))])
def delete_counterparty(counterparty_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, Counterparty, counterparty_id)
    db.delete(obj)
    db.commit()
    return {"deleted": True}
