import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids_with_role,
    resolve_write_company_id,
)
from app.config import settings
from app.crypto import decrypt_field, encrypt_field
from app.database import get_db
from app.fx import convert_to_rub
from app.integrations.amocrm import AmoCrmClient, AmoCrmError, map_contact, map_lead
from app.integrations.tbank import TBankClient, TBankError, map_operation
from app.models import (
    Account,
    AutomationRule,
    Category,
    Counterparty,
    Integration,
    Project,
    RoleEnum,
    Transaction,
    TxTypeEnum,
    User,
)
from app.schemas import (
    AmoCrmConnectIn,
    AmoCrmSyncIn,
    AmoCrmSyncResult,
    AutomationRuleIn,
    AutomationRuleOut,
    IntegrationConnectIn,
    IntegrationOut,
    IntegrationSyncIn,
    IntegrationSyncResult,
)
from app.utils import get_or_404_accessible

router = APIRouter(tags=["automation"])

ADMIN_ONLY = [RoleEnum.admin]
FINANCE_MODULE = Depends(require_module("finance"))

# Каталог поддерживаемых интеграций из README (roadmap Этап 5). Строки создаются
# лениво при первом обращении к /integrations, если их ещё нет в БД — на компанию.
INTEGRATION_CATALOG = [
    ("tinkoff", "Т-Банк", "bank"),
    ("alfa", "Альфа-Банк", "bank"),
    ("wildberries", "Wildberries", "marketplace"),
    ("ozon", "Ozon", "marketplace"),
    ("yookassa", "ЮKassa", "acquiring"),
    ("amocrm", "amoCRM", "crm"),
    ("1c", "1С:УНФ", "accounting"),
]

# На данный момент реально реализован синк для Т-Банка (см. app/integrations/tbank.py)
# и amoCRM (см. app/integrations/amocrm.py, отдельные /connect-amocrm и /sync-amocrm —
# у amoCRM другая форма учётных данных: OAuth2 с refresh_token, а не один статичный токен)
SYNC_SUPPORTED_PROVIDERS = {"tinkoff"}


def _get_rule_or_404(db: Session, user: User, rule_id: str) -> AutomationRule:
    return get_or_404_accessible(db, AutomationRule, rule_id, get_accessible_company_ids(db, user), "Правило не найдено")


def _validate_rule_action(db: Session, action_json: dict, company_id: str) -> None:
    # set_category/set_project переопределяют поля операции при срабатывании
    # правила (см. automation_engine.apply_rules) — обе ссылки обязаны
    # принадлежать той же компании, что и само правило, иначе можно было бы
    # незаметно проставить в операцию статью/проект другой компании.
    category_id = (action_json or {}).get("set_category")
    if category_id:
        get_or_404_accessible(db, Category, category_id, [company_id], "Статья не найдена")
    project_id = (action_json or {}).get("set_project")
    if project_id:
        get_or_404_accessible(db, Project, project_id, [company_id], "Проект не найден")


def _get_integration_or_404(db: Session, user: User, integration_id: str) -> Integration:
    return get_or_404_accessible(
        db, Integration, integration_id, get_accessible_company_ids(db, user), "Интеграция не найдена"
    )


def _ensure_integration_catalog(db: Session, company_id: str) -> None:
    existing = {i.provider for i in db.query(Integration).filter(Integration.company_id == company_id).all()}
    for provider, _label, integration_type in INTEGRATION_CATALOG:
        if provider not in existing:
            db.add(Integration(company_id=company_id, provider=provider, type=integration_type))
    db.commit()


def _get_or_create_import_category(db: Session, tx_type: TxTypeEnum, company_id: str) -> Category:
    name = "Импорт из банка (приход)" if tx_type == "income" else "Импорт из банка (расход)"
    category = db.query(Category).filter(Category.company_id == company_id, Category.name == name).first()
    if category is None:
        category = Category(company_id=company_id, name=name, group_name="Импорт", type=tx_type)
        db.add(category)
        db.flush()
    return category


def _get_or_create_counterparty(db: Session, name: str, company_id: str) -> Counterparty:
    counterparty = db.query(Counterparty).filter(Counterparty.company_id == company_id, Counterparty.name == name).first()
    if counterparty is None:
        counterparty = Counterparty(company_id=company_id, name=name)
        db.add(counterparty)
        db.flush()
    return counterparty


@router.get("/automation-rules", response_model=list[AutomationRuleOut], dependencies=[FINANCE_MODULE])
def list_rules(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids_with_role(db, user, company_id, ADMIN_ONLY)
    return db.query(AutomationRule).filter(AutomationRule.company_id.in_(company_ids)).all()


@router.post("/automation-rules", response_model=AutomationRuleOut, dependencies=[FINANCE_MODULE])
def create_rule(
    payload: AutomationRuleIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # condition_json / action_json: {"field": "counterparty", "op": "contains", "value": "Wildberries"}
    # (или список таких условий — все должны выполняться) → {"set_category": "...", "set_project": "..."}
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    _validate_rule_action(db, payload.action_json, target)
    rule = AutomationRule(**payload.model_dump(), company_id=target, created_by=user.id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/automation-rules/{rule_id}", response_model=AutomationRuleOut, dependencies=[FINANCE_MODULE])
def update_rule(
    rule_id: str, payload: AutomationRuleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    rule = _get_rule_or_404(db, user, rule_id)
    check_company_role(db, user, rule.company_id, ADMIN_ONLY)
    _validate_rule_action(db, payload.action_json, rule.company_id)
    for field, value in payload.model_dump().items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/automation-rules/{rule_id}", dependencies=[FINANCE_MODULE])
def delete_rule(rule_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rule = _get_rule_or_404(db, user, rule_id)
    check_company_role(db, user, rule.company_id, ADMIN_ONLY)
    db.delete(rule)
    db.commit()
    return {"deleted": True}


@router.get("/integrations", response_model=list[IntegrationOut], dependencies=[FINANCE_MODULE])
def list_integrations(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids_with_role(db, user, company_id, ADMIN_ONLY)
    for cid in company_ids:
        _ensure_integration_catalog(db, cid)
    return (
        db.query(Integration)
        .filter(Integration.company_id.in_(company_ids))
        .order_by(Integration.provider)
        .all()
    )


@router.post("/integrations/{integration_id}/connect", response_model=IntegrationOut, dependencies=[FINANCE_MODULE])
def connect_integration(
    integration_id: str,
    payload: IntegrationConnectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    integration = _get_integration_or_404(db, user, integration_id)
    check_company_role(db, user, integration.company_id, ADMIN_ONLY)
    if not payload.token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен обязателен")
    integration.credentials_encrypted = encrypt_field(payload.token)
    integration.is_connected = True
    db.commit()
    db.refresh(integration)
    return integration


@router.post(
    "/integrations/{integration_id}/disconnect", response_model=IntegrationOut, dependencies=[FINANCE_MODULE]
)
def disconnect_integration(
    integration_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    integration = _get_integration_or_404(db, user, integration_id)
    check_company_role(db, user, integration.company_id, ADMIN_ONLY)
    integration.credentials_encrypted = None
    integration.is_connected = False
    db.commit()
    db.refresh(integration)
    return integration


@router.post("/integrations/{integration_id}/sync", response_model=IntegrationSyncResult, dependencies=[FINANCE_MODULE])
def sync_integration(
    integration_id: str,
    payload: IntegrationSyncIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    integration = _get_integration_or_404(db, user, integration_id)
    check_company_role(db, user, integration.company_id, ADMIN_ONLY)
    company_id = integration.company_id
    if not integration.is_connected or not integration.credentials_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Интеграция не подключена")
    if integration.provider not in SYNC_SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Синхронизация для этого провайдера пока не реализована",
        )

    account = get_or_404_accessible(db, Account, payload.account_id, [company_id], "Счёт не найден")
    if not account.account_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У счёта не указан номер счёта — заполните его в справочнике «Счета»",
        )

    token = decrypt_field(integration.credentials_encrypted)
    if token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось расшифровать токен интеграции")

    client = TBankClient(base_url=settings.tbank_base_url, token=token)

    created = 0
    skipped_duplicate = 0
    skipped_no_fx_rate = 0
    skipped_unparseable = 0
    try:
        for raw_op in client.fetch_all_operations(account.account_number, payload.date_from, payload.date_to):
            mapped = map_operation(raw_op)
            if mapped is None:
                skipped_unparseable += 1
                continue

            if (
                db.query(Transaction)
                .filter(Transaction.company_id == company_id, Transaction.external_ref == mapped["external_ref"])
                .first()
            ):
                skipped_duplicate += 1
                continue

            amount_rub = convert_to_rub(db, account.currency, mapped["amount"], mapped["date_odds"])
            if amount_rub is None:
                # Нет курса на дату операции — пропускаем, не блокируя остальной синк;
                # такие операции можно будет добавить вручную после загрузки курса.
                skipped_no_fx_rate += 1
                continue

            tx_type = TxTypeEnum(mapped["type"])
            category = _get_or_create_import_category(db, tx_type, company_id)
            counterparty_id = None
            if mapped["counterparty_name"]:
                counterparty_id = _get_or_create_counterparty(db, mapped["counterparty_name"], company_id).id

            db.add(
                Transaction(
                    company_id=company_id,
                    date_odds=mapped["date_odds"],
                    account_id=account.id,
                    category_id=category.id,
                    counterparty_id=counterparty_id,
                    type=tx_type,
                    amount=mapped["amount"],
                    currency=account.currency,
                    amount_rub=amount_rub,
                    comment=mapped["comment"],
                    external_ref=mapped["external_ref"],
                    created_by=user.id,
                )
            )
            created += 1
    except TBankError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    skipped = skipped_duplicate + skipped_no_fx_rate + skipped_unparseable
    integration.last_sync_at = datetime.utcnow()
    db.commit()
    log_action(
        db,
        user,
        action="sync",
        entity_type="integration",
        entity_id=integration.id,
        details={"created": created, "skipped": skipped, "account_id": account.id},
        company_id=company_id,
    )
    return IntegrationSyncResult(
        created=created,
        skipped=skipped,
        skipped_duplicate=skipped_duplicate,
        skipped_no_fx_rate=skipped_no_fx_rate,
        skipped_unparseable=skipped_unparseable,
    )


# ---------------------------------------------------------------------------
# amoCRM — отдельные эндпоинты, а не общие /connect и /sync: у amoCRM другая форма
# учётных данных (OAuth2: client_id/secret + access/refresh token, а не один статичный
# токен, как у Т-Банка) и другая логика синка (контакты → контрагенты, сделки → доходные
# транзакции, а не банковская выписка по счёту).
# ---------------------------------------------------------------------------


@router.post("/integrations/{integration_id}/connect-amocrm", response_model=IntegrationOut, dependencies=[FINANCE_MODULE])
def connect_amocrm(
    integration_id: str,
    payload: AmoCrmConnectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    integration = _get_integration_or_404(db, user, integration_id)
    check_company_role(db, user, integration.company_id, ADMIN_ONLY)
    if integration.provider != "amocrm":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Эта интеграция не amoCRM")

    integration.credentials_encrypted = encrypt_field(json.dumps(payload.model_dump()))
    integration.is_connected = True
    db.commit()
    db.refresh(integration)
    return integration


@router.post("/integrations/{integration_id}/sync-amocrm", response_model=AmoCrmSyncResult, dependencies=[FINANCE_MODULE])
def sync_amocrm(
    integration_id: str,
    payload: AmoCrmSyncIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    integration = _get_integration_or_404(db, user, integration_id)
    check_company_role(db, user, integration.company_id, ADMIN_ONLY)
    company_id = integration.company_id
    if integration.provider != "amocrm":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Эта интеграция не amoCRM")
    if not integration.is_connected or not integration.credentials_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Интеграция не подключена")

    account = get_or_404_accessible(db, Account, payload.account_id, [company_id], "Счёт не найден")

    creds_raw = decrypt_field(integration.credentials_encrypted)
    if creds_raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось расшифровать данные интеграции")
    creds = json.loads(creds_raw)

    client = AmoCrmClient(
        subdomain=creds["subdomain"],
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        access_token=creds["access_token"],
        refresh_token=creds["refresh_token"],
        redirect_uri=creds.get("redirect_uri", "https://localhost/"),
    )

    contacts_created = 0
    contacts_matched = 0
    deals_created = 0
    deals_skipped = 0
    contact_names_by_id: dict[int, str] = {}

    try:
        for raw_contact in client.fetch_all_contacts():
            mapped = map_contact(raw_contact)
            if mapped is None:
                continue
            contact_names_by_id[mapped["id"]] = mapped["name"]
            already_existed = (
                db.query(Counterparty)
                .filter(Counterparty.company_id == company_id, Counterparty.name == mapped["name"])
                .first()
                is not None
            )
            _get_or_create_counterparty(db, mapped["name"], company_id)
            if already_existed:
                contacts_matched += 1
            else:
                contacts_created += 1
        db.flush()

        for raw_lead in client.fetch_all_leads(date_from=payload.date_from):
            mapped = map_lead(raw_lead)
            if mapped is None:
                deals_skipped += 1
                continue

            if (
                db.query(Transaction)
                .filter(Transaction.company_id == company_id, Transaction.external_ref == mapped["external_ref"])
                .first()
            ):
                deals_skipped += 1
                continue

            amount_rub = convert_to_rub(db, account.currency, mapped["amount"], mapped["date_odds"])
            if amount_rub is None:
                deals_skipped += 1
                continue

            category = _get_or_create_import_category(db, TxTypeEnum.income, company_id)
            counterparty_id = None
            contact_name = contact_names_by_id.get(mapped["contact_id"])
            if contact_name:
                counterparty_id = _get_or_create_counterparty(db, contact_name, company_id).id

            db.add(
                Transaction(
                    company_id=company_id,
                    date_odds=mapped["date_odds"],
                    account_id=account.id,
                    category_id=category.id,
                    counterparty_id=counterparty_id,
                    type=TxTypeEnum.income,
                    amount=mapped["amount"],
                    currency=account.currency,
                    amount_rub=amount_rub,
                    comment=mapped["comment"],
                    external_ref=mapped["external_ref"],
                    created_by=user.id,
                )
            )
            deals_created += 1
    except AmoCrmError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    if client.tokens_refreshed:
        creds["access_token"] = client.access_token
        creds["refresh_token"] = client.refresh_token
        integration.credentials_encrypted = encrypt_field(json.dumps(creds))

    integration.last_sync_at = datetime.utcnow()
    db.commit()
    log_action(
        db,
        user,
        action="sync",
        entity_type="integration",
        entity_id=integration.id,
        details={"contacts_created": contacts_created, "deals_created": deals_created, "account_id": account.id},
        company_id=company_id,
    )
    return AmoCrmSyncResult(
        contacts_created=contacts_created,
        contacts_matched=contacts_matched,
        deals_created=deals_created,
        deals_skipped=deals_skipped,
    )
