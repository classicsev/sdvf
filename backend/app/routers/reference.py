from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids,
    resolve_write_company_id,
)
from app.config import settings
from app.database import get_db
from app.holding_transfers import get_or_create_internal_transfer_category
from app.integrations.sdvf import SdvfClient, SdvfError
from app.models import (
    Account,
    Category,
    Company,
    CompanyMember,
    Counterparty,
    CounterpartyContact,
    PayrollAccrual,
    PayrollPayment,
    Planning,
    Project,
    RoleEnum,
    Transaction,
    TxTypeEnum,
    User,
)
from app.schemas import (
    AccountIn,
    AccountOut,
    AccountSetCurrentBalanceIn,
    CategoryIn,
    CategoryOut,
    CounterpartyContactIn,
    CounterpartyContactOut,
    CounterpartyIn,
    CounterpartyOut,
    CounterpartySdvfLinkIn,
    CounterpartySyncResult,
    MoveCompanyIn,
    ProjectIn,
    ProjectOut,
    SdvfCounterpartyOut,
)
from app.utils import delete_or_deactivate, get_or_404_accessible, move_to_company

router = APIRouter(tags=["reference"])

ADMIN_ONLY = [RoleEnum.admin]


def _get_or_404(db: Session, user: User, model, entity_id: str):
    return get_or_404_accessible(db, model, entity_id, get_accessible_company_ids(db, user))


def _move_to_company(db, user, obj, payload: MoveCompanyIn, references: list[tuple[type, str]]):
    """Перенос справочной записи в другую компанию — только между компаниями,
    где пользователь admin (и в исходной, и в целевой: иначе можно было бы
    "подарить" запись в компанию, которой не управляешь, или наоборот забрать
    чужую), и только пока запись ничем не используется (см. move_to_company)."""
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    check_company_role(db, user, payload.company_id, ADMIN_ONLY)
    move_to_company(db, obj, payload.company_id, references)
    db.refresh(obj)
    return obj


# ---------------------------------------------------------------------------
# Статьи (категории)
# ---------------------------------------------------------------------------


@router.get("/categories", response_model=list[CategoryOut], dependencies=[Depends(require_module("finance"))])
def list_categories(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    # Категории "Перевод между своими счетами" заводим лениво здесь (а не только
    # когда авто-детект перевода первый раз сработает при импорте) — иначе их
    # нечем было бы выбрать вручную, пока такой случай не встретится сам.
    for cid in company_ids:
        get_or_create_internal_transfer_category(db, TxTypeEnum.income, cid)
        get_or_create_internal_transfer_category(db, TxTypeEnum.expense, cid)
    db.commit()
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


@router.patch(
    "/categories/{category_id}/company",
    response_model=CategoryOut,
    dependencies=[Depends(require_module("finance"))],
)
def move_category_company(
    category_id: str,
    payload: MoveCompanyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_or_404(db, user, Category, category_id)
    return _move_to_company(db, user, obj, payload, [(Transaction, "category_id"), (Planning, "category_id")])


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


@router.patch(
    "/projects/{project_id}/company", response_model=ProjectOut, dependencies=[Depends(require_module("finance"))]
)
def move_project_company(
    project_id: str,
    payload: MoveCompanyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_or_404(db, user, Project, project_id)
    return _move_to_company(
        db,
        user,
        obj,
        payload,
        [
            (Transaction, "project_id"),
            (Planning, "project_id"),
            (PayrollAccrual, "project_id"),
            (CompanyMember, "project_id"),
        ],
    )


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


@router.post(
    "/accounts/{account_id}/set-current-balance",
    response_model=AccountOut,
    dependencies=[Depends(require_module("finance"))],
)
def set_account_current_balance(
    account_id: str,
    payload: AccountSetCurrentBalanceIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Вместо поиска исторического остатка на дату первой синхронизированной
    операции — пользователь вводит остаток, который видит в банке ПРЯМО СЕЙЧАС
    (или на любую другую as_of), и мы сами решаем уравнение
    opening_balance = current_balance − (доход − расход по уже введённым
    операциям на эту дату), чтобы расчётный остаток в Учёте совпал день в день."""
    obj = _get_or_404(db, user, Account, account_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)

    as_of = payload.as_of or date.today()
    flow = (
        db.query(
            func.sum(
                case(
                    (Transaction.type == TxTypeEnum.income, Transaction.amount),
                    else_=-Transaction.amount,
                )
            )
        )
        .filter(Transaction.account_id == obj.id, Transaction.date_odds <= as_of)
        .scalar()
    ) or Decimal("0")

    obj.opening_balance = payload.current_balance - flow
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/accounts/{account_id}", dependencies=[Depends(require_module("finance"))])
def delete_account(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _get_or_404(db, user, Account, account_id)
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    deleted = delete_or_deactivate(db, obj, [(Transaction, "account_id"), (PayrollPayment, "account_id")])
    return {"deleted": deleted, "deactivated": not deleted}


@router.patch(
    "/accounts/{account_id}/company", response_model=AccountOut, dependencies=[Depends(require_module("finance"))]
)
def move_account_company(
    account_id: str,
    payload: MoveCompanyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_or_404(db, user, Account, account_id)
    return _move_to_company(
        db, user, obj, payload, [(Transaction, "account_id"), (PayrollPayment, "account_id")]
    )


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


@router.patch(
    "/counterparties/{counterparty_id}/company",
    response_model=CounterpartyOut,
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def move_counterparty_company(
    counterparty_id: str,
    payload: MoveCompanyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_or_404(db, user, Counterparty, counterparty_id)
    # CounterpartyContact хранит свой собственный company_id (не наследует его
    # от контрагента) — перенос "потерял" бы контакты в старой компании, поэтому
    # блокируем, пока они есть, так же как и при наличии операций.
    return _move_to_company(
        db, user, obj, payload, [(Transaction, "counterparty_id"), (CounterpartyContact, "counterparty_id")]
    )


# ---------------------------------------------------------------------------
# Контактные лица контрагента — в карточке первична организация, контакты
# подвязываются к ней (как в amoCRM: контакт всегда принадлежит компании).
# ---------------------------------------------------------------------------


@router.post(
    "/counterparties/{counterparty_id}/contacts",
    response_model=CounterpartyContactOut,
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def create_contact(
    counterparty_id: str,
    payload: CounterpartyContactIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    counterparty = _get_or_404(db, user, Counterparty, counterparty_id)
    check_company_role(db, user, counterparty.company_id, ADMIN_ONLY)
    contact = CounterpartyContact(
        **payload.model_dump(),
        counterparty_id=counterparty.id,
        company_id=counterparty.company_id,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.patch(
    "/counterparty-contacts/{contact_id}",
    response_model=CounterpartyContactOut,
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def update_contact(
    contact_id: str,
    payload: CounterpartyContactIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contact = _get_or_404(db, user, CounterpartyContact, contact_id)
    check_company_role(db, user, contact.company_id, ADMIN_ONLY)
    for k, v in payload.model_dump().items():
        setattr(contact, k, v)
    db.commit()
    db.refresh(contact)
    return contact


@router.delete(
    "/counterparty-contacts/{contact_id}",
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def delete_contact(contact_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contact = _get_or_404(db, user, CounterpartyContact, contact_id)
    check_company_role(db, user, contact.company_id, ADMIN_ONLY)
    db.delete(contact)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Синхронизация контрагентов с СДВФ. СДВФ — источник истины по реквизитам:
# при совпадении ИНН его данные перетирают то, что пришло из amoCRM.
# ---------------------------------------------------------------------------


def _sdvf_client_or_503() -> SdvfClient:
    if not settings.sdvf_base_url or not settings.sdvf_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Интеграция с СДВФ не настроена"
        )
    return SdvfClient(settings.sdvf_base_url, settings.sdvf_api_key)


def _company_org_inn_or_400(db: Session, company_id: str) -> str:
    company = db.get(Company, company_id)
    if not company.sdvf_org_inn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите ИНН организации в настройках компании (Модули) — по нему находится ваш аккаунт в СДВФ",
        )
    return company.sdvf_org_inn


def _normalized_name(value: Optional[str]) -> str:
    """Название для сопоставления карточек: без кавычек, регистра и лишних
    пробелов. 'ООО "АЗИЗИ"' и 'ООО АЗИЗИ' — одна и та же организация."""
    text = (value or "").lower()
    for ch in ('"', "«", "»", "'", ".", ","):
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _apply_sdvf_data(counterparty: Counterparty, buyer: dict) -> None:
    """СДВФ первичен: заполненные поля оттуда затирают локальные. Пустые в СДВФ
    не стирают уже известные нам данные (частичная карточка не должна обеднять)."""
    counterparty.name = buyer.get("naming") or counterparty.name
    counterparty.inn = buyer.get("inn") or counterparty.inn
    counterparty.kpp = buyer.get("kpp") or counterparty.kpp
    counterparty.ogrn = buyer.get("ogrn") or counterparty.ogrn
    counterparty.address = buyer.get("address") or counterparty.address
    counterparty.phone = buyer.get("phone") or counterparty.phone
    counterparty.sdvf_buyer_id = buyer["id"]
    counterparty.sdvf_synced_at = datetime.utcnow()


@router.get(
    "/sdvf/counterparties",
    response_model=list[SdvfCounterpartyOut],
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def list_sdvf_counterparties(
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Карточки из СДВФ — для ручной привязки местного контрагента к существующей.
    Уже привязанные помечаются linked_counterparty_id, чтобы одну карточку СДВФ
    не прицепили к двум разным контрагентам."""
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    org_inn = _company_org_inn_or_400(db, target)
    try:
        items = _sdvf_client_or_503().list_counterparties(org_inn)
    except SdvfError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    linked = {
        c.sdvf_buyer_id: c.id
        for c in db.query(Counterparty).filter(
            Counterparty.company_id == target, Counterparty.sdvf_buyer_id.isnot(None)
        )
    }
    return [SdvfCounterpartyOut(**item, linked_counterparty_id=linked.get(item["id"])) for item in items]


@router.post(
    "/counterparties/{counterparty_id}/link-sdvf",
    response_model=CounterpartyOut,
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def link_counterparty_to_sdvf(
    counterparty_id: str,
    payload: CounterpartySdvfLinkIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Привязать карточку к существующей в СДВФ и подтянуть оттуда реквизиты."""
    counterparty = _get_or_404(db, user, Counterparty, counterparty_id)
    check_company_role(db, user, counterparty.company_id, ADMIN_ONLY)
    org_inn = _company_org_inn_or_400(db, counterparty.company_id)

    already = (
        db.query(Counterparty)
        .filter(
            Counterparty.company_id == counterparty.company_id,
            Counterparty.sdvf_buyer_id == payload.sdvf_buyer_id,
            Counterparty.id != counterparty.id,
        )
        .first()
    )
    if already:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Эта карточка СДВФ уже привязана к контрагенту «{already.name}»",
        )

    try:
        items = _sdvf_client_or_503().list_counterparties(org_inn)
    except SdvfError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    buyer = next((i for i in items if i["id"] == payload.sdvf_buyer_id), None)
    if buyer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Карточка в СДВФ не найдена")

    _apply_sdvf_data(counterparty, buyer)
    db.commit()
    db.refresh(counterparty)
    return counterparty


@router.post(
    "/counterparties/{counterparty_id}/create-in-sdvf",
    response_model=CounterpartyOut,
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def create_counterparty_in_sdvf(
    counterparty_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Завести карточку в СДВФ по данным из Учёта. Если контрагент с таким ИНН
    там уже есть, СДВФ вернёт существующий — получится привязка, а не дубль."""
    counterparty = _get_or_404(db, user, Counterparty, counterparty_id)
    check_company_role(db, user, counterparty.company_id, ADMIN_ONLY)
    if not counterparty.inn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="У контрагента не указан ИНН — он обязателен для СДВФ"
        )
    org_inn = _company_org_inn_or_400(db, counterparty.company_id)

    try:
        buyer = _sdvf_client_or_503().get_or_create_counterparty(
            inn=counterparty.inn,
            naming=counterparty.name,
            kpp=counterparty.kpp,
            ogrn=counterparty.ogrn,
            address=counterparty.address,
            phone=counterparty.phone,
            organization_inn=org_inn,
        )
    except SdvfError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    counterparty.sdvf_buyer_id = buyer["id"]
    counterparty.sdvf_synced_at = datetime.utcnow()
    db.commit()
    db.refresh(counterparty)
    return counterparty


@router.post(
    "/counterparties/sync-sdvf",
    response_model=CounterpartySyncResult,
    dependencies=[Depends(require_module("finance", "warehouse"))],
)
def sync_counterparties_with_sdvf(
    company_id: Optional[str] = None,
    create_missing: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Сверка с СДВФ по ИНН. Что делает:
    1) карточки СДВФ, которых нет в Учёте — заводит у нас;
    2) совпавшие по ИНН — привязывает и обновляет реквизиты из СДВФ (он первичен);
    3) create_missing=true — те, что есть только у нас, заводит в СДВФ.
    Контрагенты без ИНН пропускаются: сверять их не по чему.
    """
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    org_inn = _company_org_inn_or_400(db, target)
    client = _sdvf_client_or_503()

    try:
        sdvf_items = client.list_counterparties(org_inn)
    except SdvfError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    local = db.query(Counterparty).filter(Counterparty.company_id == target).all()
    local_by_inn = {c.inn: c for c in local if c.inn}
    # Карточки без ИНН (типично для пришедших из amoCRM) — сводим по названию,
    # иначе синк создал бы рядом второй экземпляр той же организации. Только без
    # ИНН: если ИНН есть и он другой — это разные юрлица с похожим названием.
    local_by_name = {}
    for c in local:
        if not c.inn and not c.sdvf_buyer_id:
            local_by_name.setdefault(_normalized_name(c.name), c)
    result = CounterpartySyncResult()

    for buyer in sdvf_items:
        inn = (buyer.get("inn") or "").strip()
        if not inn:
            result.skipped_no_inn += 1
            continue

        existing = local_by_inn.get(inn)
        if existing is None:
            # pop — одна локальная карточка достаётся только одному контрагенту
            # СДВФ: в самом СДВФ встречаются тёзки-дубли, и без этого второй
            # перехватил бы уже занятую карточку.
            existing = local_by_name.pop(_normalized_name(buyer["naming"]), None)

        if existing is None:
            created = Counterparty(company_id=target, name=buyer["naming"], inn=inn, type="debtor")
            _apply_sdvf_data(created, buyer)
            db.add(created)
            local_by_inn[inn] = created
            result.linked_by_inn += 1
        else:
            _apply_sdvf_data(existing, buyer)
            local_by_inn[inn] = existing
            result.updated_from_sdvf += 1

    if create_missing:
        for counterparty in local:
            if counterparty.sdvf_buyer_id or not counterparty.is_active:
                continue
            if not counterparty.inn:
                result.skipped_no_inn += 1
                continue
            try:
                buyer = client.get_or_create_counterparty(
                    inn=counterparty.inn,
                    naming=counterparty.name,
                    kpp=counterparty.kpp,
                    ogrn=counterparty.ogrn,
                    address=counterparty.address,
                    phone=counterparty.phone,
                    organization_inn=org_inn,
                )
            except SdvfError as exc:
                # Одна битая карточка (например, ИНН не проходит валидацию СДВФ)
                # не должна ронять весь синк — остальные всё равно пройдут.
                result.failed += 1
                result.errors.append(f"{counterparty.name}: {exc}")
                continue
            counterparty.sdvf_buyer_id = buyer["id"]
            counterparty.sdvf_synced_at = datetime.utcnow()
            result.created_in_sdvf += 1

    db.commit()
    return result
