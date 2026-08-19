import json
from datetime import date, datetime, timedelta
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
from app.bank_import import (
    get_or_create_counterparty,
    get_or_create_import_category,
    import_mapped_transactions,
)
from app.config import settings
from app.crypto import decrypt_field, encrypt_field
from app.database import get_db
from app.fx import convert_to_rub
from app.integrations.alfabank import AlfaBankClient, AlfaBankError
from app.integrations.alfabank import map_operation as map_alfa_operation
from app.integrations.amocrm import AmoCrmClient, AmoCrmError, map_company, map_contact, map_lead
from app.integrations.tbank import TBankClient, TBankError, map_operation
from app.models import (
    Account,
    AutomationRule,
    Category,
    Counterparty,
    CounterpartyContact,
    Integration,
    Project,
    RoleEnum,
    Transaction,
    TxTypeEnum,
    User,
)
from app.schemas import (
    AlfaBankConnectIn,
    AmoCrmConnectIn,
    AmoCrmSyncIn,
    AmoCrmSyncResult,
    AutomationRuleIn,
    AutomationRuleOut,
    IntegrationConnectIn,
    IntegrationOut,
    IntegrationSyncAllResult,
    IntegrationSyncIn,
    IntegrationSyncResult,
)
from app.reference_scope import get_visible_or_404
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

# На данный момент реально реализован синк для Т-Банка и Альфа-Банка (см.
# app/integrations/tbank.py, app/integrations/alfabank.py) и amoCRM (см.
# app/integrations/amocrm.py, отдельные /connect-amocrm и /sync-amocrm —
# у amoCRM другая форма учётных данных: OAuth2 с refresh_token, а не один статичный токен)
SYNC_SUPPORTED_PROVIDERS = {"tinkoff", "alfa"}
BANK_PROVIDERS = {"tinkoff", "alfa"}


def _get_rule_or_404(db: Session, user: User, rule_id: str) -> AutomationRule:
    return get_or_404_accessible(db, AutomationRule, rule_id, get_accessible_company_ids(db, user), "Правило не найдено")


def _validate_rule_action(db: Session, action_json: dict, company_id: str) -> None:
    # set_category/set_project переопределяют поля операции при срабатывании
    # правила (см. automation_engine.apply_rules) — обе ссылки обязаны
    # принадлежать той же компании, что и само правило, иначе можно было бы
    # незаметно проставить в операцию статью/проект другой компании.
    category_id = (action_json or {}).get("set_category")
    if category_id:
        get_visible_or_404(db, Category, category_id, [company_id], "Статья не найдена")
    project_id = (action_json or {}).get("set_project")
    if project_id:
        get_visible_or_404(db, Project, project_id, [company_id], "Проект не найден")


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


def _sync_bank_integration(
    db: Session,
    user: User,
    integration: Integration,
    account: Account,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    account_number_override: Optional[str] = None,
) -> IntegrationSyncResult:
    """Синхронизирует одну банковскую интеграцию с одним счётом.
    Обновляет integration.last_sync_at и integration.account_id.

    account_number_override — только для запроса к банку (напр. песочница
    Alfa API принимает лишь свои фиксированные тестовые номера счетов) — сам
    Account и его настоящий account_number в справочнике не трогаем."""
    if not integration.is_connected or not integration.credentials_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Интеграция не подключена")
    if integration.provider not in SYNC_SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Синхронизация для этого провайдера пока не реализована",
        )

    account_number = account_number_override or account.account_number
    if not account_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У счёта не указан номер счёта — заполните его в справочнике «Счета»",
        )

    creds_raw = decrypt_field(integration.credentials_encrypted)
    if creds_raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось расшифровать данные интеграции")

    if integration.provider == "alfa":
        if date_from is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для Альфа-Банка нужно указать дату начала периода — выписка запрашивается по дням",
            )
        # Alfa API отдаёт выписку строго по одному дню за запрос (см.
        # AlfaBankClient.fetch_all_operations) — широкий диапазон означает
        # столько же последовательных обращений к банку и рискует затянуться
        # на минуты. Ограничиваем один вызов синка тремя месяцами, для
        # бóльшего периода — синкать несколькими вызовами по частям.
        days_requested = ((date_to or date.today()) - date_from).days
        if days_requested > 92:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Для Альфа-Банка за один раз можно синкать не больше 92 дней "
                    "(выписка запрашивается по дням) — сузьте период и повторите частями"
                ),
            )

    try:
        # client.fetch_all_operations(...) вызывается ЗДЕСЬ, внутри try — это
        # генератор, сам HTTP-запрос уходит только при первом next() внутри
        # import_mapped_transactions ниже, поэтому исключение из него ловится
        # тем же except, что и ошибки самого импорта.
        if integration.provider == "tinkoff":
            client = TBankClient(base_url=settings.tbank_base_url, token=creds_raw)
            raw_ops = client.fetch_all_operations(account_number, date_from, date_to)
            mapped_ops = (map_operation(raw_op) for raw_op in raw_ops)
        else:  # "alfa"
            creds = json.loads(creds_raw)
            client = AlfaBankClient(
                base_url=settings.alfabank_base_url,
                api_key=creds["api_key"],
                cert_pem=creds["cert_pem"],
                key_pem=creds["key_pem"],
                key_password=creds["key_password"],
            )
            raw_ops = client.fetch_all_operations(account_number, date_from, date_to)
            mapped_ops = (map_alfa_operation(raw_op) for raw_op in raw_ops)

        result = import_mapped_transactions(db, user, integration.company_id, account, mapped_ops)
    except (TBankError, AlfaBankError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    integration.last_sync_at = datetime.utcnow()
    integration.account_id = account.id
    db.commit()
    log_action(
        db,
        user,
        action="sync",
        entity_type="integration",
        entity_id=integration.id,
        details={"created": result["created"], "skipped": result["skipped"], "account_id": account.id},
        company_id=integration.company_id,
    )
    return IntegrationSyncResult(**result)


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
    if integration.provider == "alfa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для Альфа-Банка используйте отдельную форму подключения (сертификат + ключ + API-ключ)",
        )
    if not payload.token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен обязателен")
    integration.credentials_encrypted = encrypt_field(payload.token)
    integration.is_connected = True
    db.commit()
    db.refresh(integration)
    return integration


@router.post(
    "/integrations/{integration_id}/connect-alfabank", response_model=IntegrationOut, dependencies=[FINANCE_MODULE]
)
def connect_alfabank(
    integration_id: str,
    payload: AlfaBankConnectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    integration = _get_integration_or_404(db, user, integration_id)
    check_company_role(db, user, integration.company_id, ADMIN_ONLY)
    if integration.provider != "alfa":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Эта интеграция не Альфа-Банк")
    integration.credentials_encrypted = encrypt_field(json.dumps(payload.model_dump()))
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
    account = get_or_404_accessible(db, Account, payload.account_id, [integration.company_id], "Счёт не найден")
    # Запоминаем счёт на интеграции (integration.account_id) — дальше он используется
    # для автосинка при открытии страниц (см. sync_all_integrations), без повторного
    # выбора счёта пользователем каждый раз.
    return _sync_bank_integration(
        db, user, integration, account, payload.date_from, payload.date_to, payload.account_number_override
    )


@router.post("/integrations/sync-all", response_model=IntegrationSyncAllResult, dependencies=[FINANCE_MODULE])
def sync_all_integrations(
    company_id: Optional[str] = None,
    force: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Синк всех подключённых банковских интеграций разом — без отдельного
    планировщика/крона. Вызывается фронтендом при открытии Операций и
    справочника Счетов (см. HANDOVER.md), поэтому по умолчанию (force=False)
    реально идёт в банк не чаще integration.autosync_interval_minutes — большинство
    вызовов при обычной навигации по страницам просто сверяют время и выходят,
    не тратя лимит запросов к банку. force=True (кнопка «Синхронизировать
    сейчас») игнорирует этот таймер, но не историю целиком — тянет только
    с последнего синка, как и обычный автовызов.
    """
    company_ids = resolve_company_ids_with_role(db, user, company_id, ADMIN_ONLY)
    integrations = (
        db.query(Integration)
        .filter(
            Integration.company_id.in_(company_ids),
            Integration.is_connected.is_(True),
            Integration.provider.in_(SYNC_SUPPORTED_PROVIDERS),
        )
        .all()
    )

    processed = 0
    skipped = 0
    skipped_rate_limited = 0
    errors = 0
    results: list[IntegrationSyncResult] = []
    now = datetime.utcnow()

    for integration in integrations:
        if not integration.account_id:
            # Ещё ни разу не синкали вручную с выбором счёта — автосинку нечего
            # использовать, пока пользователь не сделает первый ручной /sync.
            skipped += 1
            continue

        if not force and integration.last_sync_at:
            elapsed_minutes = (now - integration.last_sync_at).total_seconds() / 60
            if elapsed_minutes < integration.autosync_interval_minutes:
                skipped_rate_limited += 1
                continue

        account = db.get(Account, integration.account_id)
        if account is None or not account.account_number:
            skipped += 1
            continue

        # Инкрементально с прошлого синка (с суточным нахлёстом на случай пограничных
        # операций), а не вся история — иначе каждое открытие страницы гоняло бы
        # банковский API по годам транзакций.
        date_from = (integration.last_sync_at.date() - timedelta(days=1)) if integration.last_sync_at else None
        try:
            result = _sync_bank_integration(db, user, integration, account, date_from, None)
            results.append(result)
            processed += 1
        except HTTPException:
            errors += 1

    total = len(integrations)
    message = (
        f"Синхронизировано интеграций: {processed} из {total}"
        + (f", пропущено по таймеру: {skipped_rate_limited}" if skipped_rate_limited else "")
        + (f", с ошибкой: {errors}" if errors else "")
    )
    return IntegrationSyncAllResult(
        total_integrations=total,
        processed=processed,
        skipped=skipped,
        skipped_rate_limited=skipped_rate_limited,
        errors=errors,
        results=results,
        message=message,
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
    companies_created = 0
    companies_matched = 0
    kept_sdvf_data = 0
    deals_created = 0
    deals_skipped = 0
    # amoCRM company id -> наша карточка контрагента, чтобы подвязать контакты
    counterparty_by_amo_company: dict[int, Counterparty] = {}
    # amoCRM contact id -> карточка контрагента, к которой относится этот контакт.
    # Сделка приходит со ссылкой на контакт, а платит всегда организация — по этой
    # карте транзакция ложится на компанию контакта, а не на само физлицо.
    counterparty_by_amo_contact: dict[int, Counterparty] = {}

    try:
        # 1) Компании amoCRM → карточки контрагентов. Компания первична: контакты
        # ниже вешаются на неё, а не заводятся отдельными контрагентами.
        for raw_company in client.fetch_all_companies():
            mapped = map_company(raw_company)
            if mapped is None:
                continue

            counterparty = (
                db.query(Counterparty)
                .filter(Counterparty.company_id == company_id, Counterparty.amocrm_company_id == mapped["id"])
                .first()
            )
            if counterparty is None:
                # Совпадение по названию — карточка могла быть заведена руками
                # или прийти из СДВФ раньше; связываем, а не плодим дубль.
                counterparty = (
                    db.query(Counterparty)
                    .filter(Counterparty.company_id == company_id, Counterparty.name == mapped["name"])
                    .first()
                )
                if counterparty is None:
                    counterparty = Counterparty(company_id=company_id, name=mapped["name"])
                    db.add(counterparty)
                    companies_created += 1
                else:
                    companies_matched += 1
                counterparty.amocrm_company_id = mapped["id"]
            else:
                companies_matched += 1

            # СДВФ первичен: если карточка уже связана с ним, реквизиты из амо
            # не перетираем — иначе документы уйдут с данными из CRM, а не из ЕГРЮЛ.
            if counterparty.sdvf_buyer_id:
                kept_sdvf_data += 1
            else:
                counterparty.phone = mapped["phone"] or counterparty.phone
                counterparty.email = mapped["email"] or counterparty.email
                counterparty.address = mapped["address"] or counterparty.address

            db.flush()
            counterparty_by_amo_company[mapped["id"]] = counterparty

        # 2) Контакты amoCRM → контактные лица своей компании. Контакт без
        # компании становится карточкой-физлицом (иначе он потеряется).
        for raw_contact in client.fetch_all_contacts():
            mapped = map_contact(raw_contact)
            if mapped is None:
                continue

            parent = counterparty_by_amo_company.get(mapped["company_id"]) if mapped["company_id"] else None
            if parent is None:
                parent = get_or_create_counterparty(db, mapped["name"], company_id)
                if mapped["company_id"]:
                    counterparty_by_amo_company[mapped["company_id"]] = parent
            counterparty_by_amo_contact[mapped["id"]] = parent

            contact = (
                db.query(CounterpartyContact)
                .filter(
                    CounterpartyContact.company_id == company_id,
                    CounterpartyContact.amocrm_contact_id == mapped["id"],
                )
                .first()
            )
            if contact is None:
                db.add(
                    CounterpartyContact(
                        company_id=company_id,
                        counterparty_id=parent.id,
                        full_name=mapped["name"],
                        position=mapped["position"],
                        phone=mapped["phone"],
                        email=mapped["email"],
                        amocrm_contact_id=mapped["id"],
                    )
                )
                contacts_created += 1
            else:
                contact.counterparty_id = parent.id
                contact.full_name = mapped["name"]
                contact.position = mapped["position"] or contact.position
                contact.phone = mapped["phone"] or contact.phone
                contact.email = mapped["email"] or contact.email
                contacts_matched += 1
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

            category = get_or_create_import_category(db, TxTypeEnum.income, company_id)
            # Контрагент сделки — организация контакта (или он сам, если контакт
            # без компании); см. counterparty_by_amo_contact выше.
            parent = counterparty_by_amo_contact.get(mapped["contact_id"])
            counterparty_id = parent.id if parent else None

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
        companies_created=companies_created,
        companies_matched=companies_matched,
        kept_sdvf_data=kept_sdvf_data,
        deals_created=deals_created,
        deals_skipped=deals_skipped,
    )
