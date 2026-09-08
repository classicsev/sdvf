from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations.cbr_fx import CbrFxError, fetch_cbr_rate
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
    if rate is not None:
        return rate.rate_to_rub

    # Локального курса нет вообще (exchange_rates не заполняется никаким
    # ручным вводом или синком — таблица пуста, пока кто-то явно не завёл
    # курс) — тянем официальный курс ЦБ РФ на именно эту дату и кэшируем,
    # чтобы повторные операции в той же валюте/дате не ходили в ЦБ заново.
    # Сетевая ошибка ЦБ РФ не должна ронять создание операции — просто
    # ведём себя так, будто курса не нашлось (тот же 422, что и раньше).
    try:
        cbr_rate = fetch_cbr_rate(currency, on_date)
    except CbrFxError:
        return None
    if cbr_rate is None:
        return None
    if not db.query(ExchangeRate).filter(ExchangeRate.currency == currency, ExchangeRate.date == on_date).first():
        db.add(ExchangeRate(currency=currency, date=on_date, rate_to_rub=cbr_rate))
        db.flush()
    return cbr_rate


def convert_to_rub(db: Session, currency: str, amount, on_date: date) -> Optional[Decimal]:
    rate = find_rate(db, currency, on_date)
    if rate is None:
        return None
    return Decimal(str(amount)) * rate
