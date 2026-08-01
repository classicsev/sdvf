from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import get_current_user, require_roles
from app.config import settings
from app.crypto import decrypt_field, encrypt_field
from app.database import get_db
from app.fx import convert_to_rub
from app.integrations.tbank import TBankClient, TBankError, map_operation
from app.models import Account, AutomationRule, Category, Counterparty, Integration, RoleEnum, Transaction, TxTypeEnum, User
from app.schemas import (
    AutomationRuleIn,
    AutomationRuleOut,
    IntegrationConnectIn,
    IntegrationOut,
    IntegrationSyncIn,
    IntegrationSyncResult,
)
from app.utils import get_or_404

router = APIRouter(tags=["automation"])

ADMIN_ONLY = [RoleEnum.admin]

# Каталог поддерживаемых интеграций из README (roadmap Этап 5). Строки создаются
# лениво при первом обращении к /integrations, если их ещё нет в БД.
INTEGRATION_CATALOG = [
    ("tinkoff", "Т-Банк", "bank"),
    ("alfa", "Альфа-Банк", "bank"),
    ("wildberries", "Wildberries", "marketplace"),
    ("ozon", "Ozon", "marketplace"),
    ("yookassa", "ЮKassa", "acquiring"),
    ("amocrm", "amoCRM", "crm"),
    ("1c", "1С:УНФ", "accounting"),
]

# На данный момент реально реализован синк только для Т-Банка (см. app/integrations/tbank.py)
SYNC_SUPPORTED_PROVIDERS = {"tinkoff"}


def _get_rule_or_404(db: Session, rule_id: str) -> AutomationRule:
    return get_or_404(db, AutomationRule, rule_id, "Правило не найдено")


def _ensure_integration_catalog(db: Session) -> None:
    existing = {i.provider for i in db.query(Integration).all()}
    for provider, _label, integration_type in INTEGRATION_CATALOG:
        if provider not in existing:
            db.add(Integration(provider=provider, type=integration_type))
    db.commit()


def _get_or_create_import_category(db: Session, tx_type: TxTypeEnum) -> Category:
    name = "Импорт из банка (приход)" if tx_type == "income" else "Импорт из банка (расход)"
    category = db.query(Category).filter(Category.name == name).first()
    if category is None:
        category = Category(name=name, group_name="Импорт", type=tx_type)
        db.add(category)
        db.flush()
    return category


def _get_or_create_counterparty(db: Session, name: str) -> Counterparty:
    counterparty = db.query(Counterparty).filter(Counterparty.name == name).first()
    if counterparty is None:
        counterparty = Counterparty(name=name)
        db.add(counterparty)
        db.flush()
    return counterparty


@router.get("/automation-rules", response_model=list[AutomationRuleOut], dependencies=[Depends(require_roles(ADMIN_ONLY))])
def list_rules(db: Session = Depends(get_db)):
    return db.query(AutomationRule).all()


@router.post("/automation-rules", response_model=AutomationRuleOut, dependencies=[Depends(require_roles(ADMIN_ONLY))])
def create_rule(
    payload: AutomationRuleIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # condition_json / action_json: {"field": "counterparty", "op": "contains", "value": "Wildberries"}
    # (или список таких условий — все должны выполняться) → {"set_category": "...", "set_project": "..."}
    rule = AutomationRule(**payload.model_dump(), created_by=user.id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch(
    "/automation-rules/{rule_id}",
    response_model=AutomationRuleOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY))],
)
def update_rule(rule_id: str, payload: AutomationRuleIn, db: Session = Depends(get_db)):
    rule = _get_rule_or_404(db, rule_id)
    for field, value in payload.model_dump().items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/automation-rules/{rule_id}", dependencies=[Depends(require_roles(ADMIN_ONLY))])
def delete_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = _get_rule_or_404(db, rule_id)
    db.delete(rule)
    db.commit()
    return {"deleted": True}


@router.get("/integrations", response_model=list[IntegrationOut], dependencies=[Depends(require_roles(ADMIN_ONLY))])
def list_integrations(db: Session = Depends(get_db)):
    _ensure_integration_catalog(db)
    return db.query(Integration).order_by(Integration.provider).all()


@router.post(
    "/integrations/{integration_id}/connect",
    response_model=IntegrationOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY))],
)
def connect_integration(integration_id: str, payload: IntegrationConnectIn, db: Session = Depends(get_db)):
    integration = get_or_404(db, Integration, integration_id, "Интеграция не найдена")
    if not payload.token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен обязателен")
    integration.credentials_encrypted = encrypt_field(payload.token)
    integration.is_connected = True
    db.commit()
    db.refresh(integration)
    return integration


@router.post(
    "/integrations/{integration_id}/disconnect",
    response_model=IntegrationOut,
    dependencies=[Depends(require_roles(ADMIN_ONLY))],
)
def disconnect_integration(integration_id: str, db: Session = Depends(get_db)):
    integration = get_or_404(db, Integration, integration_id, "Интеграция не найдена")
    integration.credentials_encrypted = None
    integration.is_connected = False
    db.commit()
    db.refresh(integration)
    return integration


@router.post(
    "/integrations/{integration_id}/sync",
    response_model=IntegrationSyncResult,
    dependencies=[Depends(require_roles(ADMIN_ONLY))],
)
def sync_integration(
    integration_id: str,
    payload: IntegrationSyncIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    integration = get_or_404(db, Integration, integration_id, "Интеграция не найдена")
    if not integration.is_connected or not integration.credentials_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Интеграция не подключена")
    if integration.provider not in SYNC_SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Синхронизация для этого провайдера пока не реализована",
        )

    account = get_or_404(db, Account, payload.account_id, "Счёт не найден")
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
    skipped = 0
    try:
        for raw_op in client.fetch_all_operations(account.account_number, payload.date_from, payload.date_to):
            mapped = map_operation(raw_op)
            if mapped is None:
                skipped += 1
                continue

            if db.query(Transaction).filter(Transaction.external_ref == mapped["external_ref"]).first():
                skipped += 1
                continue

            amount_rub = convert_to_rub(db, account.currency, mapped["amount"], mapped["date_odds"])
            if amount_rub is None:
                # Нет курса на дату операции — пропускаем, не блокируя остальной синк;
                # такие операции можно будет добавить вручную после загрузки курса.
                skipped += 1
                continue

            tx_type = TxTypeEnum(mapped["type"])
            category = _get_or_create_import_category(db, tx_type)
            counterparty_id = None
            if mapped["counterparty_name"]:
                counterparty_id = _get_or_create_counterparty(db, mapped["counterparty_name"]).id

            db.add(
                Transaction(
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

    integration.last_sync_at = datetime.utcnow()
    db.commit()
    log_action(
        db,
        user,
        action="sync",
        entity_type="integration",
        entity_id=integration.id,
        details={"created": created, "skipped": skipped, "account_id": account.id},
    )
    return IntegrationSyncResult(created=created, skipped=skipped)
