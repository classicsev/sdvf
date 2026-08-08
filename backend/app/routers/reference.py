from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_module, require_roles
from app.database import get_db
from app.models import (
    Account,
    Category,
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
from app.utils import delete_or_deactivate, get_or_404

router = APIRouter(tags=["reference"])

ADMIN_ONLY = [RoleEnum.admin]


def _get_or_404(db: Session, model, entity_id: str, company_id: str):
    return get_or_404(db, model, entity_id, company_id=company_id)


# ---------------------------------------------------------------------------
# Статьи (категории)
# ---------------------------------------------------------------------------


@router.get("/categories", response_model=list[CategoryOut], dependencies=[Depends(require_module("finance"))])
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Category).filter(Category.company_id == user.company_id).all()


@router.post(
    "/categories",
    response_model=CategoryOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def create_category(payload: CategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Category(**payload.model_dump(), company_id=user.company_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def update_category(
    category_id: str, payload: CategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, Category, category_id, user.company_id)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/categories/{category_id}",
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def delete_category(category_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, Category, category_id, user.company_id)
    deleted = delete_or_deactivate(db, obj, [(Transaction, "category_id"), (Planning, "category_id")])
    return {"deleted": deleted, "deactivated": not deleted}


# ---------------------------------------------------------------------------
# Проекты
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut], dependencies=[Depends(require_module("finance"))])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Project).filter(Project.company_id == user.company_id).all()


@router.post(
    "/projects",
    response_model=ProjectOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def create_project(payload: ProjectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Project(**payload.model_dump(), company_id=user.company_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def update_project(
    project_id: str, payload: ProjectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, Project, project_id, user.company_id)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}",
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def delete_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, Project, project_id, user.company_id)
    deleted = delete_or_deactivate(
        db,
        obj,
        [
            (Transaction, "project_id"),
            (Planning, "project_id"),
            (PayrollAccrual, "project_id"),
            (User, "project_id"),
        ],
    )
    return {"deleted": deleted, "deactivated": not deleted}


# ---------------------------------------------------------------------------
# Счета
# ---------------------------------------------------------------------------


@router.get("/accounts", response_model=list[AccountOut], dependencies=[Depends(require_module("finance"))])
def list_accounts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Account).filter(Account.company_id == user.company_id).all()


@router.post(
    "/accounts",
    response_model=AccountOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def create_account(payload: AccountIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Account(**payload.model_dump(), company_id=user.company_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def update_account(
    account_id: str, payload: AccountIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = _get_or_404(db, Account, account_id, user.company_id)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/accounts/{account_id}",
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance"))],
)
def delete_account(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, Account, account_id, user.company_id)
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
def list_counterparties(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Counterparty).filter(Counterparty.company_id == user.company_id).all()


@router.post(
    "/counterparties",
    response_model=CounterpartyOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance", "warehouse"))],
)
def create_counterparty(
    payload: CounterpartyIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = Counterparty(**payload.model_dump(), company_id=user.company_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/counterparties/{counterparty_id}",
    response_model=CounterpartyOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance", "warehouse"))],
)
def update_counterparty(
    counterparty_id: str,
    payload: CounterpartyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_or_404(db, Counterparty, counterparty_id, user.company_id)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/counterparties/{counterparty_id}",
    dependencies=[Depends(require_roles(ADMIN_ONLY)), Depends(require_module("finance", "warehouse"))],
)
def delete_counterparty(counterparty_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, Counterparty, counterparty_id, user.company_id)
    deleted = delete_or_deactivate(db, obj, [(Transaction, "counterparty_id")])
    return {"deleted": deleted, "deactivated": not deleted}
