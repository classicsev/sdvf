from datetime import date, datetime
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict

from app.models import RoleEnum, TxTypeEnum


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


class TransactionCreate(TransactionBase):
    pass


class TransactionOut(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
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


class CategoryIn(BaseModel):
    name: str
    type: TxTypeEnum
    group_name: Optional[str] = None


class CategoryOut(CategoryIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool


class ProjectIn(BaseModel):
    name: str


class ProjectOut(ProjectIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool


class AccountIn(BaseModel):
    name: str
    currency: str = "RUB"
    opening_balance: float = 0
    account_number: Optional[str] = None


class AccountOut(AccountIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool


class CounterpartyIn(BaseModel):
    name: str
    type: str = "debtor"
    inn: Optional[str] = None


class CounterpartyOut(CounterpartyIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool


class EmployeeIn(BaseModel):
    full_name: str
    department: Optional[str] = None
    position: Optional[str] = None
    employment_type: Optional[str] = None
    bank_details: Optional[str] = None


class EmployeeOut(BaseModel):
    id: str
    full_name: str
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


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: RoleEnum
    project_id: Optional[str] = None
    is_active: bool = True


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


class IntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    type: str
    is_connected: bool
    last_sync_at: Optional[datetime] = None


class IntegrationConnectIn(BaseModel):
    token: str


class IntegrationSyncIn(BaseModel):
    account_id: str
    date_from: date
    date_to: Optional[date] = None


class IntegrationSyncResult(BaseModel):
    created: int
    skipped: int
    password: Optional[str] = None
