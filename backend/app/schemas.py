from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from app.models import OrderStatusEnum, RoleEnum, StockDirectionEnum, TxTypeEnum, WarehouseSheetTabFormat


class TransactionBase(BaseModel):
    date_odds: date
    date_opu: Optional[date] = None
    account_id: str
    category_id: str
    project_id: Optional[str] = None
    counterparty_id: Optional[str] = None
    type: TxTypeEnum
    amount: float
    currency: str
    commission: float = 0
    comment: Optional[str] = None
    # Назначение платежа из банка — отдельно от comment (своя заметка
    # пользователя). Заполняется автоматически при импорте, но остаётся
    # редактируемым. См. models.py::Transaction.bank_payment_purpose.
    bank_payment_purpose: Optional[str] = None


class TransactionCreate(TransactionBase):
    pass


class TransactionOut(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    amount_rub: float
    created_at: datetime
    created_by: Optional[str] = None
    external_ref: Optional[str] = None


class TransactionUpdate(BaseModel):
    date_odds: Optional[date] = None
    date_opu: Optional[date] = None
    account_id: Optional[str] = None
    category_id: Optional[str] = None
    project_id: Optional[str] = None
    counterparty_id: Optional[str] = None
    type: Optional[TxTypeEnum] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    commission: Optional[float] = None
    comment: Optional[str] = None
    bank_payment_purpose: Optional[str] = None


class TransactionBatchDelete(BaseModel):
    """Пакетное удаление операций — массив ID"""
    transaction_ids: list[str] = Field(..., min_items=1, max_items=1000)


class CloseMonthIn(BaseModel):
    company_id: str
    month: date  # любая дата внутри целевого месяца — используется только год/месяц


class CategoryIn(BaseModel):
    name: str
    type: TxTypeEnum
    group_name: Optional[str] = None
    is_active: bool = True
    is_financing: bool = False
    is_internal_transfer: bool = False
    # Область видимости в холдинге — по умолчанию только своя company_id (как
    # раньше). is_global=true — динамически видна во всех компаниях, включая
    # будущие. Иначе visible_company_ids — конкретные ДОПОЛНИТЕЛЬНЫЕ компании
    # (сверх своей же), см. models.py::Category.
    is_global: bool = False
    visible_company_ids: list[str] = []


class CategoryOut(CategoryIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    is_active: bool


class ProjectIn(BaseModel):
    name: str
    is_active: bool = True
    is_global: bool = False
    visible_company_ids: list[str] = []
    group_id: Optional[str] = None


class ProjectOut(ProjectIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    is_active: bool


class ProjectGroupIn(BaseModel):
    name: str
    is_active: bool = True
    is_global: bool = False
    visible_company_ids: list[str] = []


class ProjectGroupOut(ProjectGroupIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    is_active: bool


class AccountIn(BaseModel):
    name: str
    currency: str = "RUB"
    opening_balance: float = 0
    account_number: Optional[str] = None
    is_active: bool = True


class AccountOut(AccountIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    is_active: bool


class AccountSetCurrentBalanceIn(BaseModel):
    # Остаток "на сегодня" (или на as_of), который пользователь видит в
    # банковском приложении — не нужно искать исторический баланс на дату
    # первой синхронизированной операции, бэкенд сам решает уравнение
    # opening_balance = current_balance - (доход - расход по уже введённым
    # операциям), см. routers/reference.py::set_account_current_balance.
    current_balance: Decimal
    as_of: Optional[date] = None


class MoveCompanyIn(BaseModel):
    company_id: str


class BulkVisibilityIn(BaseModel):
    # Массовое "распределение" уже существующих статей/проектов по компаниям
    # холдинга — в отличие от формы редактирования (которая ПЕРЕЗАПИСЫВАЕТ
    # видимость целиком), тут ДОБАВЛЯЕМ company_ids к видимости каждой из ids,
    # не трогая то, что уже было настроено. Если is_global=true — company_ids
    # игнорируется, статьи/проекты становятся видны везде.
    ids: list[str] = Field(..., min_items=1, max_items=500)
    company_ids: list[str] = []
    is_global: bool = False


class BulkVisibilityOut(BaseModel):
    updated: int
    merged_names: list[str] = []


class CounterpartyContactIn(BaseModel):
    full_name: str
    position: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_primary: bool = False


class CounterpartyContactOut(CounterpartyContactIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    counterparty_id: str
    company_id: str
    amocrm_contact_id: Optional[int] = None


class CounterpartyIn(BaseModel):
    name: str
    type: str = "debtor"
    inn: Optional[str] = None
    is_active: bool = True
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    # Реквизиты контрагента из КНР — см. models.py::Counterparty.cn_*.
    cn_name_zh: Optional[str] = None
    cn_credit_code: Optional[str] = None
    cn_legal_rep: Optional[str] = None
    cn_address_zh: Optional[str] = None


class CounterpartyOut(CounterpartyIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    is_active: bool
    # sdvf_buyer_id пустой = карточки нет в СДВФ; фронт помечает такие и
    # предлагает привязать к существующей или создать новую (см. routers/reference.py).
    sdvf_buyer_id: Optional[int] = None
    sdvf_synced_at: Optional[datetime] = None
    amocrm_company_id: Optional[int] = None
    contacts: list[CounterpartyContactOut] = []


class SdvfCounterpartyOut(BaseModel):
    """Карточка контрагента на стороне СДВФ — для выбора при ручной привязке."""

    id: int
    naming: str
    inn: str
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    # Уже привязана к какой-то карточке в Учёте — фронт показывает такие
    # неактивными, чтобы одну карточку СДВФ не привязали к двум контрагентам.
    linked_counterparty_id: Optional[str] = None


class CounterpartySdvfLinkIn(BaseModel):
    sdvf_buyer_id: int


class CounterpartySyncResult(BaseModel):
    linked_by_inn: int = 0
    created_in_sdvf: int = 0
    updated_from_sdvf: int = 0
    skipped_no_inn: int = 0
    failed: int = 0
    errors: list[str] = []


class EmployeeIn(BaseModel):
    full_name: str
    aliases: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    employment_type: Optional[str] = None
    bank_details: Optional[str] = None


class EmployeeOut(BaseModel):
    id: str
    company_id: str
    full_name: str
    aliases: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    employment_type: Optional[str] = None
    status: str
    bank_details: Optional[str] = None


class AutomationCondition(BaseModel):
    field: str  # counterparty / comment / amount / category
    op: str  # contains / equals / gt / lt / gte / lte / not_set
    value: Optional[object] = None


class AutomationRuleIn(BaseModel):
    condition_json: Union[AutomationCondition, list[AutomationCondition]]
    action_json: dict
    is_active: bool = True


class AutomationRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    condition_json: object
    action_json: dict
    is_active: bool
    created_by: Optional[str] = None


class PlanningIn(BaseModel):
    category_id: str
    project_id: Optional[str] = None
    amount: float
    frequency: str = "monthly"  # monthly / once / weekly
    scheduled_date: date
    is_active: bool = True


class PlanningOut(PlanningIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str


class PayrollAccrualIn(BaseModel):
    employee_id: str
    project_id: Optional[str] = None
    period: date
    hourly_rate: Optional[float] = None
    salary: float = 0
    bonus: float = 0
    deductions: float = 0


class PayrollAccrualOut(PayrollAccrualIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    total: float


class PayrollPaymentIn(BaseModel):
    employee_id: str
    accrual_id: Optional[str] = None
    account_id: str
    date: date
    amount: float
    payment_type: str = "ЗП"


class PayrollPaymentOut(PayrollPaymentIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    module_finance_enabled: bool
    module_warehouse_enabled: bool
    module_china_enabled: bool = False
    sdvf_auto_generate_documents: bool = False
    sdvf_org_naming: Optional[str] = None
    sdvf_org_inn: Optional[str] = None
    sdvf_org_kpp: Optional[str] = None
    sdvf_org_ogrn: Optional[str] = None
    sdvf_org_address: Optional[str] = None
    sdvf_org_phone: Optional[str] = None
    company_type: str = "legal_entity"
    cn_org_name_zh: Optional[str] = None
    cn_org_credit_code: Optional[str] = None
    cn_org_legal_rep: Optional[str] = None
    cn_org_address_zh: Optional[str] = None
    cn_org_registered_capital: Optional[float] = None
    cn_org_established_date: Optional[date] = None
    cn_org_business_scope_zh: Optional[str] = None


class CompanyMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company: CompanyOut
    role: RoleEnum
    project_id: Optional[str] = None


class CompanyCreate(BaseModel):
    name: str
    # 'legal_entity' (по умолчанию, ООО/ИП с реквизитами) | 'individual'
    # (личные счета физлица, без обязательных юр. реквизитов)
    company_type: str = "legal_entity"


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    company_type: Optional[str] = None


class CompanyMemberCreate(BaseModel):
    email: str
    role: RoleEnum
    project_id: Optional[str] = None
    # Обязательны, только если пользователя с таким email ещё нет в системе —
    # тогда для него создаётся новый аккаунт. Если email уже существует,
    # игнорируются — пользователь просто получает доступ к этой компании.
    full_name: Optional[str] = None
    password: Optional[str] = None


class CompanyMemberUpdate(BaseModel):
    role: Optional[RoleEnum] = None
    project_id: Optional[str] = None


class CompanyModulesIn(BaseModel):
    module_finance_enabled: Optional[bool] = None
    module_warehouse_enabled: Optional[bool] = None
    module_china_enabled: Optional[bool] = None
    # Реквизиты "нашей" организации для интеграции с СДВФ (создание Счёт/УПД) —
    # вводятся один раз, см. models.py::Company.
    sdvf_org_naming: Optional[str] = None
    sdvf_org_inn: Optional[str] = None
    sdvf_org_kpp: Optional[str] = None
    sdvf_org_ogrn: Optional[str] = None
    sdvf_org_address: Optional[str] = None
    sdvf_org_phone: Optional[str] = None
    # Реквизиты компании из свидетельства о регистрации КНР (营业执照), см.
    # models.py::Company.cn_org_*.
    cn_org_name_zh: Optional[str] = None
    cn_org_credit_code: Optional[str] = None
    cn_org_legal_rep: Optional[str] = None
    cn_org_address_zh: Optional[str] = None
    cn_org_registered_capital: Optional[float] = None
    cn_org_established_date: Optional[date] = None
    cn_org_business_scope_zh: Optional[str] = None


class DadataPartyOut(BaseModel):
    """Реквизиты из ЕГРЮЛ/ЕГРИП для автозаполнения форм (см. routers/dadata.py).
    Пустые строки вместо None — фронт подставляет значения прямо в поля формы."""

    name: str
    inn: str
    kpp: str
    ogrn: str
    address: str
    party_type: str  # legal_entity | individual
    supervisor: str
    supervisor_position: str


class CompanyRegisterIn(BaseModel):
    company_name: str
    admin_email: str
    admin_full_name: str
    admin_password: str = Field(min_length=8)
    # Необязательно, без проверки в этой версии (см. README) — просто сохраняется как есть
    admin_phone: Optional[str] = None
    # Согласие на обработку персональных данных (152-ФЗ) — обязательно true,
    # иначе регистрация отклоняется на бэкенде (не только визуально на фронте)
    pdn_consent: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    company: CompanyOut
    # Все компании пользователя (см. план "Мульти-компании") — company/company_id/
    # role/project_id выше остаются для обратной совместимости и указывают на
    # "первую" (по дате создания) компанию; новый фронтенд должен работать со
    # списком companies целиком.
    companies: list[CompanyMembershipOut] = []
    email: Optional[str] = None
    full_name: str
    role: RoleEnum
    project_id: Optional[str] = None
    is_active: bool = True
    email_verified: bool = False
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    telegram: Optional[str] = None
    max_messenger: Optional[str] = None
    gender: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str
    role: RoleEnum
    project_id: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[RoleEnum] = None
    project_id: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class MyProfileUpdate(BaseModel):
    """Самостоятельное редактирование пользователем собственного профиля —
    в отличие от UserUpdate (админский эндпоинт), тут нет role/project_id/
    is_active/password: их менять себе через этот путь нельзя."""

    full_name: Optional[str] = None
    phone: Optional[str] = None
    telegram: Optional[str] = None
    max_messenger: Optional[str] = None
    gender: Optional[str] = None


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    key_prefix: str
    user_id: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


class ApiKeyCreateIn(BaseModel):
    name: str
    user_id: Optional[str] = None  # по умолчанию — сам создающий администратор


class ApiKeyCreated(ApiKeyOut):
    key: str


class IntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    account_id: Optional[str] = None
    provider: str
    type: str
    is_connected: bool
    last_sync_at: Optional[datetime] = None
    autosync_enabled: bool = False
    autosync_interval_minutes: int = 60


class IntegrationConnectIn(BaseModel):
    token: str


class IntegrationSyncIn(BaseModel):
    account_id: str
    date_from: date
    date_to: Optional[date] = None
    # Для песочниц банков, принимающих только свои фиксированные тестовые
    # номера счетов (напр. Alfa API) — не переписывать реальный номер счёта
    # в справочнике ради теста, а подставить тестовый только для этого запроса.
    account_number_override: Optional[str] = None


class IntegrationSyncResult(BaseModel):
    created: int
    skipped: int
    skipped_duplicate: int = 0
    skipped_no_fx_rate: int = 0
    skipped_unparseable: int = 0


class IntegrationSyncAllResult(BaseModel):
    total_integrations: int
    processed: int
    skipped: int
    skipped_rate_limited: int
    errors: int
    results: list[IntegrationSyncResult]
    message: str


class JumpSyncIn(BaseModel):
    account_id: str
    date_from: date
    date_to: Optional[date] = None


class JumpMatchResult(BaseModel):
    matched: int
    category_set_from_default: int
    category_set_from_rule: int
    unmatched: int
    ambiguous: int


class StatementTransactionPreview(BaseModel):
    date_odds: date
    type: TxTypeEnum
    amount: Decimal
    comment: Optional[str] = None
    counterparty_name: Optional[str] = None


class StatementImportResult(BaseModel):
    bank: str
    account_number: Optional[str] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    # Входящий остаток, который называет сама справка/выписка (есть не у всех
    # банков) — просто для отображения, не путать с account_opening_balance ниже.
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    closing_balance_date: Optional[date] = None
    # Начальный остаток СЧЁТА в Учёте после этого запроса (пересчитан автоматически,
    # см. routers/statements.py) — фронтенд обязан обновить им поле формы, иначе
    # при последующем нажатии "Сохранить" форма отправит старое значение и затрёт
    # только что применённый остаток обратно.
    account_opening_balance: Optional[Decimal] = None
    dry_run: bool
    created: int
    skipped: int
    skipped_duplicate: int = 0
    skipped_no_fx_rate: int = 0
    skipped_unparseable: int = 0
    preview: list[StatementTransactionPreview] = []


class AlfaBankConnectIn(BaseModel):
    # mTLS (сертификат+ключ клиента, выданные Альфа-Банком) + ApiKey — см.
    # integrations/alfabank.py. cert_pem/key_pem — содержимое .cer/.key файлов
    # как есть (PEM), key_password — пароль, которым зашифрован приватный ключ.
    api_key: str
    cert_pem: str
    key_pem: str
    key_password: str


class AmoCrmConnectIn(BaseModel):
    subdomain: str
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    redirect_uri: str = "https://localhost/"


class AmoCrmSyncIn(BaseModel):
    account_id: str
    date_from: Optional[date] = None


class AmoCrmSyncResult(BaseModel):
    contacts_created: int
    contacts_matched: int
    deals_created: int
    deals_skipped: int
    # Компании amoCRM → карточки контрагентов (компания первична, контакты под ней).
    companies_created: int = 0
    companies_matched: int = 0
    # Реквизиты не перезаписаны, потому что карточка привязана к СДВФ — он первичен.
    kept_sdvf_data: int = 0


# ---------------------------------------------------------------------------
# Склад
# ---------------------------------------------------------------------------


class WarehouseIn(BaseModel):
    name: str
    is_active: bool = True


class WarehouseOut(WarehouseIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str


class EquipmentIn(BaseModel):
    name: str
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    note: Optional[str] = None
    is_active: bool = True


class EquipmentOut(EquipmentIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str


class ProductIn(BaseModel):
    name: str
    unit: str = "кг"
    category: Optional[str] = None
    is_active: bool = True


class ProductOut(ProductIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str


class ProductVariantIn(BaseModel):
    product_id: str
    name: str
    is_active: bool = True


class ProductVariantOut(ProductVariantIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str


class StockMovementIn(BaseModel):
    date: date
    warehouse_id: str
    product_variant_id: str
    direction: StockDirectionEnum
    quantity: float
    note: Optional[str] = None
    executor_id: Optional[str] = None
    payroll_rate: Optional[float] = None


class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    date: date
    warehouse_id: str
    product_variant_id: str
    direction: StockDirectionEnum
    quantity: float
    note: Optional[str] = None
    executor_id: Optional[str] = None
    payroll_rate: Optional[float] = None
    payroll_accrual_id: Optional[str] = None
    order_id: Optional[str] = None
    production_run_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime


class StockTransferIn(BaseModel):
    date: date
    product_variant_id: str
    from_warehouse_id: str
    to_warehouse_id: str
    quantity: float
    note: Optional[str] = None


class WarehouseSheetConnectionIn(BaseModel):
    # Полный текст JSON-ключа service account, как скачан из Google Cloud —
    # шифруется целиком на бэкенде, никогда не хранится в открытом виде.
    credentials_json: str
    autosync_interval_minutes: int = 180


class WarehouseSheetConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    is_connected: bool
    last_sync_at: Optional[datetime] = None
    autosync_interval_minutes: int


class WarehouseSheetTabIn(BaseModel):
    spreadsheet_id: str
    spreadsheet_label: Optional[str] = None
    tab_name: str
    format: WarehouseSheetTabFormat
    product_id: Optional[str] = None
    default_warehouse_id: Optional[str] = None
    column_mapping: dict[str, str] = {}
    is_active: bool = True


class WarehouseSheetTabOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    spreadsheet_id: str
    spreadsheet_label: Optional[str] = None
    tab_name: str
    format: WarehouseSheetTabFormat
    product_id: Optional[str] = None
    default_warehouse_id: Optional[str] = None
    column_mapping: dict[str, str] = {}
    last_synced_row: int
    is_active: bool


class WarehouseSheetSyncResult(BaseModel):
    tab_id: str
    tab_name: str
    imported: int
    unresolved_employees: list[str] = []
    unresolved_warehouses: list[str] = []
    error: Optional[str] = None


class WarehouseSheetSyncAllResult(BaseModel):
    processed: int
    skipped_rate_limited: int
    results: list[WarehouseSheetSyncResult] = []
    message: str


class EmployeeMiniOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str


class StockBalanceOut(BaseModel):
    company_id: str
    warehouse_id: str
    warehouse_name: str
    product_id: str
    product_name: str
    unit: str
    product_variant_id: str
    variant_name: str
    quantity: float
    reserved: float = 0
    available: float = 0


# ---------------------------------------------------------------------------
# Заказы
# ---------------------------------------------------------------------------


class OrderLineIn(BaseModel):
    product_variant_id: str
    quantity: float
    # Для будущего 装箱单 (Packing List) — см. models.py::OrderLine, опциональны.
    package_count: Optional[int] = None
    package_type: Optional[str] = None
    gross_weight: Optional[float] = None
    net_weight: Optional[float] = None
    marks: Optional[str] = None


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_variant_id: str
    quantity: float
    package_count: Optional[int] = None
    package_type: Optional[str] = None
    gross_weight: Optional[float] = None
    net_weight: Optional[float] = None
    marks: Optional[str] = None


class OrderCreateIn(BaseModel):
    counterparty_id: str
    warehouse_id: str
    requested_date: Optional[date] = None
    note: Optional[str] = None
    # Условия сделки для будущих 合同/发票 — см. models.py::Order.
    incoterms: Optional[str] = None
    incoterms_place: Optional[str] = None
    payment_terms: Optional[str] = None
    lines: list[OrderLineIn]


class OrderUpdateIn(BaseModel):
    counterparty_id: Optional[str] = None
    requested_date: Optional[date] = None
    note: Optional[str] = None
    incoterms: Optional[str] = None
    incoterms_place: Optional[str] = None
    payment_terms: Optional[str] = None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    counterparty_id: str
    warehouse_id: str
    status: OrderStatusEnum
    requested_date: Optional[date] = None
    note: Optional[str] = None
    incoterms: Optional[str] = None
    incoterms_place: Optional[str] = None
    payment_terms: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    lines: list[OrderLineOut] = []
    sdvf_invoice_ref: Optional[dict] = None
    sdvf_utd_ref: Optional[dict] = None


class SdvfDocumentLineIn(BaseModel):
    order_line_id: str
    # Склад не хранит цену (см. models.py::OrderLine) — вводится вручную в
    # момент генерации документа, отдельно для каждого заказа.
    price: float
    nds_product: Optional[int] = None


class SdvfGenerateDocumentIn(BaseModel):
    nds: int = 0
    nds_type: str = "onTop"
    lines: list[SdvfDocumentLineIn]


class SdvfDocumentRefOut(BaseModel):
    id: int
    pdf_url: str


# ---------------------------------------------------------------------------
# Производство
# ---------------------------------------------------------------------------


class ProductionRecipeInputIn(BaseModel):
    input_variant_id: str
    qty_per_unit: float


class ProductionRecipeInputOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    input_variant_id: str
    qty_per_unit: float


class ProductionRecipeIn(BaseModel):
    name: str
    output_variant_id: str
    is_active: bool = True
    inputs: list[ProductionRecipeInputIn]


class ProductionRecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    name: str
    output_variant_id: str
    is_active: bool
    inputs: list[ProductionRecipeInputOut] = []


class ProductionRunIn(BaseModel):
    recipe_id: str
    warehouse_id: str
    date: date
    output_qty: float
    note: Optional[str] = None


class ProductionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    recipe_id: str
    warehouse_id: str
    date: date
    output_qty: float
    note: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
