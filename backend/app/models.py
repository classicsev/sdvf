import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class RoleEnum(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    payroll_operator = "payroll_operator"
    project_manager = "project_manager"
    viewer = "viewer"
    warehouse_operator = "warehouse_operator"


class TxTypeEnum(str, enum.Enum):
    income = "income"
    expense = "expense"


class StockDirectionEnum(str, enum.Enum):
    in_ = "in"
    out = "out"
    production_consume = "production_consume"
    production_yield = "production_yield"
    transfer_in = "transfer_in"
    transfer_out = "transfer_out"
    adjustment = "adjustment"


# ---------------------------------------------------------------------------
# Компании (мультитенантность)
# ---------------------------------------------------------------------------


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(300))
    # Гранулярность тарифа — по модулю; биллинга пока нет, флаги переключаются
    # вручную самой компанией на странице "Модули" (PATCH /companies/me/modules)
    module_finance_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    module_warehouse_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Автогенерация Счёт/УПД в СДВФ при отгрузке заказа — поле зарезервировано
    # на будущее (см. routers/orders.py), сейчас не используется: цены по
    # позициям заказа вводятся вручную в момент генерации, автоматический
    # источник цен отсутствует (Склад не хранит цену, только количество).
    sdvf_auto_generate_documents: Mapped[bool] = mapped_column(Boolean, default=False)
    # Реквизиты "нашей" организации для СДВФ (InformationOrganization на их
    # стороне) — вводятся один раз в настройках компании, в отличие от цен
    # (которые разные на каждый заказ). Пусто = генерация Счёт/УПД недоступна.
    sdvf_org_naming: Mapped[str] = mapped_column(String(300), nullable=True)
    sdvf_org_inn: Mapped[str] = mapped_column(String(20), nullable=True)
    sdvf_org_kpp: Mapped[str] = mapped_column(String(20), nullable=True)
    sdvf_org_ogrn: Mapped[str] = mapped_column(String(20), nullable=True)
    sdvf_org_address: Mapped[str] = mapped_column(Text, nullable=True)
    sdvf_org_phone: Mapped[str] = mapped_column(String(50), nullable=True)
    # Кто создал/владеет компанией — задел под будущие лимиты тарифа
    # ("сколько компаний на плане"), сам лимит пока не считается нигде.
    owner_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    # 'legal_entity' (ООО/ИП, с реквизитами) | 'individual' — личные счета
    # физлица, участвуют в той же отчётности наравне с компаниями, без
    # обязательных юридических реквизитов.
    company_type: Mapped[str] = mapped_column(String(20), default="legal_entity")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")  # RUB, CNY, ...
    opening_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Реальный номер р/с (20 цифр) — нужен для синка выписки через банковское API
    account_number: Mapped[str] = mapped_column(String(20), nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[TxTypeEnum] = mapped_column(Enum(TxTypeEnum))
    group_name: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Counterparty(Base):
    __tablename__ = "counterparties"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20), default="debtor")  # debtor / creditor
    inn: Mapped[str] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    full_name: Mapped[str] = mapped_column(String(300))
    department: Mapped[str] = mapped_column(String(150), nullable=True)
    position: Mapped[str] = mapped_column(String(150), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(50), nullable=True)  # ИП / Самозанятый
    status: Mapped[str] = mapped_column(String(50), default="active")
    # bank_details хранится зашифрованным на уровне приложения, не в открытом виде
    bank_details_encrypted: Mapped[str] = mapped_column(Text, nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    # email уникален глобально, не в рамках компании — логин ищет пользователя
    # только по email без выбора компании, composite-уникальность сделала бы
    # логин неоднозначным между разными компаниями. Nullable — у пользователей,
    # пришедших через OAuth (напр. VK ID), провайдер не всегда отдаёт email.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(300))
    # Nullable — у чисто-OAuth пользователей пароля нет вообще, вход только через провайдера
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Не блокирует доступ (аккаунт активен сразу) — используется только для баннера-
    # напоминания на фронте. У пользователей через OAuth ставится True сразу —
    # провайдер (VK/Яндекс/Sber) уже подтвердил личность за нас.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=True)  # без проверки в этой версии
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    telegram: Mapped[str] = mapped_column(String(100), nullable=True)
    max_messenger: Mapped[str] = mapped_column(String(100), nullable=True)
    # 'M' / 'F' / NULL — используется для согласования рода в истории задач
    # ("сделал"/"сделала"), не обязательно к заполнению.
    gender: Mapped[str] = mapped_column(String(1), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company_memberships = relationship(
        "CompanyMember", order_by="CompanyMember.created_at", back_populates="user"
    )

    # --- Обратная совместимость на время перехода (см. план "Мульти-компании") ---
    # Роутеры, ещё не переведённые на company_memberships/accessible_company_ids
    # (Фаза 2), продолжают работать как раньше — в терминах "первой" компании
    # пользователя. Новый код (routers/companies.py, дашборд) должен использовать
    # company_memberships/auth.get_accessible_company_ids напрямую, а не эти свойства.
    @property
    def _primary_membership(self) -> "CompanyMember | None":
        return self.company_memberships[0] if self.company_memberships else None

    @property
    def company_id(self) -> str | None:
        m = self._primary_membership
        return m.company_id if m else None

    @property
    def role(self) -> "RoleEnum | None":
        m = self._primary_membership
        return m.role if m else None

    @property
    def project_id(self) -> str | None:
        m = self._primary_membership
        return m.project_id if m else None

    @property
    def company(self) -> "Company | None":
        m = self._primary_membership
        return m.company if m else None

    @property
    def companies(self) -> list["CompanyMember"]:
        """Алиас для схемы UserOut.companies — сама связь называется
        company_memberships (чтобы не путать с company/company_id-заглушками выше)."""
        return self.company_memberships


class CompanyMember(Base):
    """Доступ пользователя к конкретной компании — многие-ко-многим вместо
    прежнего одиночного User.company_id. Роль и project_id теперь per-company:
    один и тот же пользователь может быть admin в одной компании и viewer в
    другой. См. план "Мульти-компании" для контекста."""

    __tablename__ = "company_members"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_company_member_user_company"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"))
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum))
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True
    )  # только для role=project_manager, скоуп внутри этой компании
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="company_memberships")
    company = relationship("Company")


class OAuthAccount(Base):
    """Связка пользователя с внешней личностью у OAuth-провайдера (VK ID /
    Яндекс ID / Sber ID). Один User может иметь несколько связок (вход и через
    VK, и через Яндекс на один и тот же аккаунт), но каждая (provider,
    provider_user_id) ведёт ровно к одному User."""

    __tablename__ = "oauth_accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(20))  # "vk" | "yandex" | "sber"
    provider_user_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_accounts_provider_user"),
    )


# ---------------------------------------------------------------------------
# Транзакционные таблицы
# ---------------------------------------------------------------------------


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    date_odds: Mapped[date] = mapped_column(Date)
    date_opu: Mapped[date] = mapped_column(Date, nullable=True)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id"))
    category_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("categories.id"))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    counterparty_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("counterparties.id"), nullable=True
    )
    type: Mapped[TxTypeEnum] = mapped_column(Enum(TxTypeEnum))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    # amount_rub фиксируется на дату операции по курсу на тот момент — не пересчитывается задним числом
    amount_rub: Mapped[float] = mapped_column(Numeric(14, 2))
    commission: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    # Ключ дедупликации для синка из внешних систем (напр. "tbank:<operationId>") —
    # NULL для операций, внесённых вручную. Уникален в рамках компании (не глобально) —
    # разные компании синкают свои собственные банки/CRM независимо.
    external_ref: Mapped[str] = mapped_column(String(150), nullable=True)

    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "external_ref", name="uq_transactions_company_id_external_ref"),
    )

    account = relationship("Account")
    category = relationship("Category")


class Planning(Base):
    __tablename__ = "planning"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    category_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("categories.id"))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly / once / weekly
    scheduled_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PayrollAccrual(Base):
    __tablename__ = "payroll_accruals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    employee_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("employees.id"))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    period: Mapped[date] = mapped_column(Date)  # первое число месяца начисления
    hourly_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    salary: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    bonus: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    deductions: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2))


class PayrollPayment(Base):
    __tablename__ = "payroll_payments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    employee_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("employees.id"))
    accrual_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("payroll_accruals.id"), nullable=True)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id"))
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    payment_type: Mapped[str] = mapped_column(String(30))  # ЗП / Аванс / Долг / Бонус


# ---------------------------------------------------------------------------
# Склад
# ---------------------------------------------------------------------------


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(20), default="кг")
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    product_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("products.id"))
    # Калибр/модификация товара, напр. "40/60" — аналог размера/цвета в обычном складском учёте
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product = relationship("Product")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    date: Mapped[date] = mapped_column(Date)
    warehouse_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouses.id"))
    product_variant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("product_variants.id"))
    # values_callable обязателен: без него SQLAlchemy сериализует enum по имени члена
    # (.name), а не по значению (.value) — для in_ ("in") они расходятся, и запросы
    # с этим значением падают на реальной БД, где тип создан со значениями ('in', ...),
    # как в миграции.
    direction: Mapped[StockDirectionEnum] = mapped_column(
        Enum(StockDirectionEnum, values_callable=lambda enum_cls: [e.value for e in enum_cls])
    )
    quantity: Mapped[float] = mapped_column(Numeric(12, 3))
    note: Mapped[str] = mapped_column(Text, nullable=True)
    # Мост с зарплатой: если заполнены оба поля, при создании движения автоматически
    # создаётся PayrollAccrual на executor_id (quantity * payroll_rate) — аналог
    # "ЗП = вес улова * ставка" из ручного складского учёта, но через модуль "Зарплата"
    executor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("employees.id"), nullable=True)
    payroll_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    payroll_accrual_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("payroll_accruals.id"), nullable=True
    )
    # Заполняется автоматически при отгрузке заказа (см. Order.ship) — движение
    # "расход", созданное как следствие заказа, а не введённое вручную
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("orders.id"), nullable=True)
    # Заполняется автоматически при производственной партии (см. ProductionRun) —
    # расход сырья по техкарте и приход готового продукта
    production_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("production_runs.id"), nullable=True
    )

    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    warehouse = relationship("Warehouse")
    product_variant = relationship("ProductVariant")


class OrderStatusEnum(str, enum.Enum):
    draft = "draft"
    reserved = "reserved"
    shipped = "shipped"
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    counterparty_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("counterparties.id"))
    warehouse_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouses.id"))
    status: Mapped[OrderStatusEnum] = mapped_column(
        Enum(OrderStatusEnum, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=OrderStatusEnum.draft,
    )
    requested_date: Mapped[date] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # {"id": <sdvf document id>, "pdf_url": "..."} — результат генерации в СДВФ
    # (см. integrations/sdvf.py), чтобы повторный клик не плодил дубли документа.
    sdvf_invoice_ref: Mapped[dict] = mapped_column(JSONB, nullable=True)
    sdvf_utd_ref: Mapped[dict] = mapped_column(JSONB, nullable=True)

    lines = relationship("OrderLine", cascade="all, delete-orphan", backref="order")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("orders.id"))
    product_variant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("product_variants.id"))
    quantity: Mapped[float] = mapped_column(Numeric(12, 3))


class ProductionRecipe(Base):
    __tablename__ = "production_recipes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    # Единственный выходной вариант техкарты — аналог одной колонки листа "Цех"
    # (напр. "мидия глазированная п/ст")
    output_variant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("product_variants.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    inputs = relationship("ProductionRecipeInput", cascade="all, delete-orphan", backref="recipe")


class ProductionRecipeInput(Base):
    __tablename__ = "production_recipe_inputs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    recipe_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("production_recipes.id"))
    input_variant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("product_variants.id"))
    # Норма расхода input_variant на 1 единицу выходного варианта техкарты
    qty_per_unit: Mapped[float] = mapped_column(Numeric(12, 4))


class ProductionRun(Base):
    __tablename__ = "production_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    recipe_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("production_recipes.id"))
    warehouse_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouses.id"))
    date: Mapped[date] = mapped_column(Date)
    output_qty: Mapped[float] = mapped_column(Numeric(12, 3))
    note: Mapped[str] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Автоматизация и аудит
# ---------------------------------------------------------------------------


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    condition_json: Mapped[dict] = mapped_column(JSONB)
    action_json: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    provider: Mapped[str] = mapped_column(String(50))  # tinkoff / alfa / wildberries / ozon / amocrm / 1c
    type: Mapped[str] = mapped_column(String(50))  # bank / marketplace / crm / accounting
    # credentials хранится зашифрованным, никогда в открытом виде
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    # Первые символы ключа — для опознания в списке, полный ключ показывается только один раз при создании
    key_prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Запросы с этим ключом получают ровно те же права, что и у user_id (роль, RLS) —
    # ключ не отдельная сущность доступа, а альтернативный способ аутентификации существующего пользователя
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100), nullable=True)
    details_json: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    currency: Mapped[str] = mapped_column(String(3))
    rate_to_rub: Mapped[float] = mapped_column(Numeric(10, 4))
    date: Mapped[date] = mapped_column(Date)
