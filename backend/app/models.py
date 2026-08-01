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


class TxTypeEnum(str, enum.Enum):
    income = "income"
    expense = "expense"


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")  # RUB, CNY, ...
    opening_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Реальный номер р/с (20 цифр) — нужен для синка выписки через банковское API
    account_number: Mapped[str] = mapped_column(String(20), nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[TxTypeEnum] = mapped_column(Enum(TxTypeEnum))
    group_name: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Counterparty(Base):
    __tablename__ = "counterparties"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20), default="debtor")  # debtor / creditor
    inn: Mapped[str] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
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
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(300))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum))
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True
    )  # только для project_manager
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Транзакционные таблицы
# ---------------------------------------------------------------------------


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
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
    # NULL для операций, внесённых вручную.
    external_ref: Mapped[str] = mapped_column(String(150), nullable=True, unique=True)

    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, onupdate=datetime.utcnow)

    account = relationship("Account")
    category = relationship("Category")


class Planning(Base):
    __tablename__ = "planning"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    category_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("categories.id"))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly / once / weekly
    scheduled_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PayrollAccrual(Base):
    __tablename__ = "payroll_accruals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
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
    employee_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("employees.id"))
    accrual_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("payroll_accruals.id"), nullable=True)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id"))
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    payment_type: Mapped[str] = mapped_column(String(30))  # ЗП / Аванс / Долг / Бонус


# ---------------------------------------------------------------------------
# Автоматизация и аудит
# ---------------------------------------------------------------------------


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    condition_json: Mapped[dict] = mapped_column(JSONB)
    action_json: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    provider: Mapped[str] = mapped_column(String(50))  # tinkoff / alfa / wildberries / ozon / amocrm / 1c
    type: Mapped[str] = mapped_column(String(50))  # bank / marketplace / crm / accounting
    # credentials хранится зашифрованным, никогда в открытом виде
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
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
