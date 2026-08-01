from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ExchangeRate


def find_rate(db: Session, currency: str, on_date: date) -> Optional[Decimal]:
    if currency == "RUB":
        return Decimal("1")

    # Курс фиксируется на дату операции — берём последний известный курс на эту
    # дату или раньше (см. README: "не пересчитывается задним числом").
    rate = (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency == currency, ExchangeRate.date <= on_date)
        .order_by(ExchangeRate.date.desc())
        .first()
    )
    return rate.rate_to_rub if rate else None


def convert_to_rub(db: Session, currency: str, amount, on_date: date) -> Optional[Decimal]:
    rate = find_rate(db, currency, on_date)
    if rate is None:
        return None
    return Decimal(str(amount)) * rate
