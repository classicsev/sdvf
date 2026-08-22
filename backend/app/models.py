import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
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
    # Работа с КНР: реквизиты компаний, зарегистрированных в Китае (см.
    # cn_org_*), и двуязычные (RU/中文) документы для китайских контрагентов.
    # Независим от company_type — включается и российской компанией, которая
    # просто торгует с КНР, не только теми, что сами зарегистрированы там.
    module_china_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
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
    # обязательных юридических реквизитов | 'cn_legal_entity' — компания,
    # зарегистрированная в КНР (营业执照), свои реквизиты — см. cn_org_*.
    company_type: Mapped[str] = mapped_column(String(20), default="legal_entity")
    # Реквизиты компании из свидетельства о регистрации КНР (营业执照) —
    # заполняются, только если company_type == 'cn_legal_entity'. Единый
    # соц.-кредитный код (统一社会信用代码) заменяет собой ИНН+ОГРН разом —
    # в КНР других номеров у юрлица нет.
    cn_org_name_zh: Mapped[str] = mapped_column(String(300), nullable=True)
    cn_org_credit_code: Mapped[str] = mapped_column(String(32), nullable=True)
    cn_org_legal_rep: Mapped[str] = mapped_column(String(200), nullable=True)
    cn_org_address_zh: Mapped[str] = mapped_column(Text, nullable=True)
    cn_org_registered_capital: Mapped[float] = mapped_column(Numeric(14, 2), nullable=True)
    cn_org_established_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    cn_org_business_scope_zh: Mapped[str] = mapped_column(Text, nullable=True)
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
    # Финансовая деятельность (займы/кредитные линии и их погашение) — не доход
    # и не расход бизнеса ни при УСН-доходы (пп.10 п.1 ст.251 НК РФ), ни при ОСН,
    # поэтому исключается из П&Л и сводного Прихода/Расхода на дашборде, но сама
    # операция остаётся видна в списке — деньги реально прошли по счёту.
    is_financing: Mapped[bool] = mapped_column(Boolean, default=False)
    # Перевод между своими же счетами/компаниями/физлицами в этом же холдинге
    # (см. app/holding_transfers.py) — деньги не "заработаны" и не "потрачены",
    # просто переложены из одного кармана в другой. Как и is_financing,
    # исключается из П&Л/Приход-Расход на любом уровне (одна компания или все
    # сразу — свои переводы не выручка ни там, ни там), но остаётся в списке
    # операций и в остатке счёта.
    is_internal_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    # Видна и выбираема во ВСЕХ компаниях холдинга — динамически, включая те,
    # что появятся позже (не снимок текущего списка). company_id остаётся
    # "владеющей" компанией — редактировать статью может только её admin,
    # даже если сама статья глобальная. Когда is_global=False, но статья всё
    # равно нужна в нескольких (не всех) компаниях — см. category_companies.
    is_global: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_companies = relationship("Company", secondary="category_companies", viewonly=True)

    @property
    def visible_company_ids(self) -> list[str]:
        return [c.id for c in self.visible_companies]


class CategoryCompany(Base):
    """Доп. компании, где статья выбираема, помимо своей же company_id —
    только когда is_global=False (иначе избыточно, статья и так видна везде).
    """

    __tablename__ = "category_companies"

    category_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("categories.id"), primary_key=True)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"), primary_key=True)


class ProjectGroup(Base):
    """Группа проектов — уровень иерархии выше Project (например, «Пчёлы» как
    сезонное направление, внутри которого заводятся проекты по месяцам).
    is_global/visible_companies — тот же паттерн кросс-компанийной видимости,
    что у Category/Project (см. ниже), чтобы не было несогласованности:
    остальные справочники это умеют, группы проектов тоже должны."""

    __tablename__ = "project_groups"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_companies = relationship("Company", secondary="project_group_companies", viewonly=True)

    @property
    def visible_company_ids(self) -> list[str]:
        return [c.id for c in self.visible_companies]


class ProjectGroupCompany(Base):
    __tablename__ = "project_group_companies"

    project_group_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("project_groups.id"), primary_key=True
    )
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"), primary_key=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # См. Category.is_global/CategoryCompany — то же самое для проектов.
    is_global: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_companies = relationship("Company", secondary="project_companies", viewonly=True)
    # Группа проектов (см. ProjectGroup) — необязательная, старые проекты
    # (в т.ч. «Пчёлы») сознательно не мигрируются автоматически.
    group_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("project_groups.id"), nullable=True)

    @property
    def visible_company_ids(self) -> list[str]:
        return [c.id for c in self.visible_companies]


class ProjectCompany(Base):
    __tablename__ = "project_companies"

    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), primary_key=True)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"), primary_key=True)


class Counterparty(Base):
    """Карточка контрагента-организации. Первична именно организация, контакты
    (физлица) подвязываются к ней — см. CounterpartyContact. Источник истины по
    реквизитам — СДВФ: если карточка связана с Buyer в СДВФ (sdvf_buyer_id), при
    синхронизации его данные перетирают пришедшие из amoCRM."""

    __tablename__ = "counterparties"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20), default="debtor")  # debtor / creditor
    inn: Mapped[str] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Реквизиты — те же поля, что у Buyer в СДВФ, чтобы карточки совпадали
    # один в один и документы уходили с верными данными.
    kpp: Mapped[str] = mapped_column(String(20), nullable=True)
    ogrn: Mapped[str] = mapped_column(String(20), nullable=True)
    address: Mapped[str] = mapped_column(Text, nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)

    # Реквизиты контрагента из КНР — заполняются, если контрагент сам
    # зарегистрирован в Китае (см. Company.cn_org_* — тот же набор полей,
    # только на стороне покупателя/поставщика, не своей организации).
    # Нужны как Seller/Buyer на будущих двуязычных документах (合同/发票/装箱单,
    # см. HANDOVER.md — модуль "Китай", основа под документы).
    cn_name_zh: Mapped[str] = mapped_column(String(300), nullable=True)
    cn_credit_code: Mapped[str] = mapped_column(String(32), nullable=True)
    cn_legal_rep: Mapped[str] = mapped_column(String(200), nullable=True)
    cn_address_zh: Mapped[str] = mapped_column(Text, nullable=True)

    # Связи с внешними системами. sdvf_buyer_id пустой = карточка ещё не заведена
    # в СДВФ (на фронте помечается как несинхронизированная, с кнопками
    # "привязать к существующей" / "создать в СДВФ").
    sdvf_buyer_id: Mapped[int] = mapped_column(Integer, nullable=True)
    sdvf_synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    amocrm_company_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    # Статья/проект по умолчанию для операций с этим контрагентом — заполняются
    # не вручную отдельной формой, а сами запоминаются, когда пользователь
    # поправляет статью/проект у операции, сопоставленной с Jump.Finance (см.
    # jump_matching.py и routers/transactions.py::update_transaction). При
    # следующем сопоставлении с тем же контрагентом подставляются автоматически.
    default_category_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("categories.id"), nullable=True
    )
    default_project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True
    )

    contacts: Mapped[list["CounterpartyContact"]] = relationship(
        back_populates="counterparty", cascade="all, delete-orphan"
    )


class CounterpartyContact(Base):
    """Контактное лицо в организации-контрагенте (как в amoCRM: контакт всегда
    принадлежит компании). Контакт из amoCRM без компании контрагентом не
    становится — заводится карточка-физлицо, а контакт вешается на неё."""

    __tablename__ = "counterparty_contacts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    counterparty_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("counterparties.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(300))
    position: Mapped[str] = mapped_column(String(150), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    amocrm_contact_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    counterparty: Mapped["Counterparty"] = relationship(back_populates="contacts")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    full_name: Mapped[str] = mapped_column(String(300))
    # Прозвища/сокращения из реальных источников (напр. Google-таблиц), через
    # запятую — резолв исполнителя при синке (warehouse_sheets.py::resolve_employee)
    # проверяет их наравне со словами full_name, чтобы не заводить нового
    # сотрудника под "Женя Цихм", когда это уже "Женя Цихмейструк".
    aliases: Mapped[str] = mapped_column(String(300), nullable=True)
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
    # Назначение платежа из банковской выписки — отдельно от comment (это уже
    # СВОЯ заметка пользователя). Раньше банковский текст писался прямо в
    # comment, из-за чего некуда было деть собственный комментарий, не потеряв
    # оригинальный текст банка. Заполняется только при импорте (bank_import.py),
    # но остаётся редактируемым — если банк/OCR распознал не совсем то.
    bank_payment_purpose: Mapped[str] = mapped_column(Text, nullable=True)
    # Ключ дедупликации для синка из внешних систем (напр. "tbank:<operationId>") —
    # NULL для операций, внесённых вручную. Уникален в рамках компании (не глобально) —
    # разные компании синкают свои собственные банки/CRM независимо.
    external_ref: Mapped[str] = mapped_column(String(150), nullable=True)
    # id выплаты в Jump.Finance, с которой сопоставлена ЭТА (уже существующая,
    # пришедшая из банка) операция — см. jump_matching.py. Не участвует в
    # дедупликации при импорте (это не источник самой операции, а обогащение
    # задним числом), только помечает "уже сопоставлено", чтобы не сопоставлять
    # повторно при следующем автозапуске после синка Т-Банка.
    jump_payment_id: Mapped[str] = mapped_column(String(50), nullable=True)

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


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(300))
    # Реальные данные вперемешку: "3" (шт по умолчанию), "1,5рул", "20м", "много" —
    # количество не всегда чистое число, поэтому храним как есть, без принудительного
    # разбора на число+единицу (см. import-скрипт: то, что распозналось как число,
    # идёт в quantity, остаток строки — в quantity_unit; "много" целиком в unit).
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    quantity_unit: Mapped[str] = mapped_column(String(50), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
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


class WarehouseSheetConnection(Base):
    """Доступ компании к Google Sheets (склад) — один service-account ключ на
    компанию, им читаются/пишутся все привязанные листы (см. WarehouseSheetTab),
    независимо от того, в какой конкретно таблице лежит каждый лист."""

    __tablename__ = "warehouse_sheet_connections"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id"))
    # JSON-ключ служебного аккаунта Google — тот же паттерн, что и PEM-сертификат
    # Альфа-Банка в Integration.credentials_encrypted (см. app/crypto.py).
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    autosync_interval_minutes: Mapped[int] = mapped_column(Integer, default=180)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)


class WarehouseSheetTabFormat(str, enum.Enum):
    movements = "movements"  # универсальный шаблон: 1 строка = 1 движение склада
    wide_calibers_in = "wide_calibers_in"  # легаси-лист прихода (калибры по столбцам)
    wide_calibers_out = "wide_calibers_out"  # легаси-лист расхода
    processing_wide = "processing_wide"  # легаси "Цех" (SKU по столбцам, знак = приход/расход)


class WarehouseSheetTab(Base):
    """Один синхронизируемый лист одной Google-таблицы. Несколько строк могут
    указывать на РАЗНЫЕ spreadsheet_id под одним WarehouseSheetConnection —
    например, легаси-листы реальной рабочей таблицы и листы новой
    таблицы-шаблона синкаются одним и тем же service-account ключом."""

    __tablename__ = "warehouse_sheet_tabs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    connection_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouse_sheet_connections.id"))
    spreadsheet_id: Mapped[str] = mapped_column(String(100))
    spreadsheet_label: Mapped[str] = mapped_column(String(200), nullable=True)
    tab_name: Mapped[str] = mapped_column(String(200))
    format: Mapped[WarehouseSheetTabFormat] = mapped_column(
        Enum(WarehouseSheetTabFormat, values_callable=lambda enum_cls: [e.value for e in enum_cls])
    )
    # Только для wide_calibers_*/processing_wide — лист привязан к одному виду товара.
    product_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("products.id"), nullable=True)
    default_warehouse_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouses.id"), nullable=True)
    # Для wide_calibers_*/processing_wide — JSON-конфиг колонок листа по БУКВЕ
    # столбца (не по названию заголовка — реальные легаси-листы неоднородны,
    # с повторяющимися заголовками и несколькими под-таблицами в одном листе).
    # Формат см. в app/warehouse_sheets.py (модуль-докстринг). Для format ==
    # movements не используется (колонки шаблона фиксированы).
    column_mapping_json: Mapped[str] = mapped_column(Text, nullable=True)
    # Курсор — последняя прочитанная строка листа, не "уже виденные" по
    # содержимому: у строк нет естественного уникального ключа, а строки
    # только дописываются в конец (подтверждено на реальных данных).
    last_synced_row: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    connection = relationship("WarehouseSheetConnection")


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
    # Кто везёт — реальные листы ("Отгрузки календарь") ведут план по дням с
    # именем курьера в каждой строке; не привязан к Employee/ЗП, это просто
    # оперативная пометка "кто везёт эту отгрузку".
    courier: Mapped[str] = mapped_column(String(200), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    # Условия сделки для будущих 合同 (Sales Contract) / 商业发票 (Commercial
    # Invoice) — см. HANDOVER.md, модуль "Китай", основа под документы.
    # incoterms — код термина (FOB/CIF/CFR/EXW и т.п.), incoterms_place —
    # поименованный порт/место по Инкотермс (например, "FOB Владивосток").
    incoterms: Mapped[str] = mapped_column(String(10), nullable=True)
    incoterms_place: Mapped[str] = mapped_column(String(200), nullable=True)
    payment_terms: Mapped[str] = mapped_column(Text, nullable=True)
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
    # Для будущего 装箱单 (Packing List) — Склад сейчас не различает физическую
    # упаковку (только абстрактное количество в единице товара), эти поля
    # заполняются отдельно, обычно уже на этапе подготовки к отгрузке, а не
    # при создании заказа. См. HANDOVER.md, модуль "Китай", основа под
    # документы — UI для их заполнения пока не строился намеренно.
    package_count: Mapped[int] = mapped_column(Integer, nullable=True)
    package_type: Mapped[str] = mapped_column(String(50), nullable=True)  # CTN / PLT / BOX и т.п.
    gross_weight: Mapped[float] = mapped_column(Numeric(12, 3), nullable=True)
    net_weight: Mapped[float] = mapped_column(Numeric(12, 3), nullable=True)
    marks: Mapped[str] = mapped_column(Text, nullable=True)  # 唛头 — маркировка мест


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
    account_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50))  # tinkoff / alfa / wildberries / ozon / amocrm / 1c
    type: Mapped[str] = mapped_column(String(50))  # bank / marketplace / crm / accounting
    # credentials хранится зашифрованным, никогда в открытом виде
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    autosync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    autosync_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)


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
