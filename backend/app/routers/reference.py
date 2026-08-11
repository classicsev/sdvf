from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids,
    resolve_write_company_id,
)
from app.database import get_db
from app.models import (
    Account,
    Category,
    CompanyMember,
    Counterparty,
    PayrollAccrual,
    PayrollPayment,
    Planning,
    Project,
    RoleEnum,
    Transaction,
    User,
)
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
from app.utils import delete_or_deactivate, get_or_404_accessible

router = APIRouter(tags=["reference"])

ADMIN_ONLY = [RoleEnum.admin]


def _get_or_404(db: Session, user: User, model, entity_id: str):
    return get_or_404_accessible(db, model, entity_id, get_accessible_company_ids(db, user))


# ---------------------------------------------------------------------------
# Статьи (категории)
# ---------------------------------------------------------------------------


@router.get("/categories", response_model=list[CategoryOut], dependencies=[Depends(require_module("finance"))])
def list_categories(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return db.query(Category).filter(Category.company_id.in_(company_ids)).all()


@router.post("/categories", response_model=CategoryOut, dependencies=[Depends(require_module("finance"))])
def create_category(
    payload: CategoryIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    obj = Category(**payload.model_dump(), company_id=target)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/categories/{category_id}", response_model=CategoryOut, dependencies=[Depends(require_module("finance"))]
)
def update_category(
    category_id: str, payload: CategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, user, Category, category_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/categories/{category_id}", dependencies=[Depends(require_module("finance"))])
def delete_category(category_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, user, Category, category_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    deleted = delete_or_deactivate(db, obj, [(Transaction, "category_id"), (Planning, "category_id")])
    return {"deleted": deleted, "deactivated": not deleted}


# ---------------------------------------------------------------------------
# Проекты
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut], dependencies=[Depends(require_module("finance"))])
def list_projects(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return db.query(Project).filter(Project.company_id.in_(company_ids)).all()


@router.post("/projects", response_model=ProjectOut, dependencies=[Depends(require_module("finance"))])
def create_project(
    payload: ProjectIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    obj = Project(**payload.model_dump(), company_id=target)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/projects/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_module("finance"))]
)
def update_project(
    project_id: str, payload: ProjectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, user, Project, project_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/projects/{project_id}", dependencies=[Depends(require_module("finance"))])
def delete_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, user, Project, project_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    deleted = delete_or_deactivate(
        db,
        obj,
        [
            (Transaction, "project_id"),
            (Planning, "project_id"),
            (PayrollAccrual, "project_id"),
            (CompanyMember, "project_id"),
        ],
    )
    return {"deleted": deleted, "deactivated": not deleted}


# ---------------------------------------------------------------------------
# Счета
# ---------------------------------------------------------------------------


@router.get("/accounts", response_model=list[AccountOut], dependencies=[Depends(require_module("finance"))])
def list_accounts(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return db.query(Account).filter(Account.company_id.in_(company_ids)).all()


@router.post("/accounts", response_model=AccountOut, dependencies=[Depends(require_module("finance"))])
def create_account(
    payload: AccountIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    obj = Account(**payload.model_dump(), company_id=target)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/accounts/{account_id}", response_model=AccountOut, dependencies=[Depends(require_module("finance"))]
)
def update_account(
    account_id: str, payload: AccountIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, user, Account, account_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/accounts/{account_id}", dependencies=[Depends(require_module("finance"))])
def delete_account(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, user, Account, account_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    deleted = delete_or_deactivate(db, obj, [(Transaction, "account_id"), (PayrollPayment, "account_id")])
    return {"deleted": deleted, "deactivated": not deleted}


# ---------------------------------------------------------------------------
# Контрагенты — общий ресурс: нужен и Учёту (операции), и Складу (заказы)
# ---------------------------------------------------------------------------


@router.get(
    "/counterparties",
    response_model=list[CounterpartyOut],
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def list_counterparties(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return db.query(Counterparty).filter(Counterparty.company_id.in_(company_ids)).all()


@router.post(
    "/counterparties",
    response_model=CounterpartyOut,
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def create_counterparty(
    payload: CounterpartyIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    obj = Counterparty(**payload.model_dump(), company_id=target)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/counterparties/{counterparty_id}",
    response_model=CounterpartyOut,
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def update_counterparty(
    counterparty_id: str,
    payload: CounterpartyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_or_404(db, user, Counterparty, counterparty_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/counterparties/{counterparty_id}",
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def delete_counterparty(counterparty_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, user, Counterparty, counterparty_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    deleted = delete_or_deactivate(db, obj, [(Transaction, "counterparty_id")])
    return {"deleted": deleted, "deactivated": not deleted}
