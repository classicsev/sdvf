"""Повторяющиеся плановые операции — единственный фоновый джоб в проекте.

Решение (см. план "Пассивы/капитал.../recurring"): APScheduler в процессе
backend, не Celery+beat — однопроцессный uvicorn на одном сервере, нагрузка
по расписанию мизерная, отдельный worker+beat контейнер ради одной задачи
избыточен. Джоб создаёт обычную Transaction (payment_confirmed=False,
accrual_confirmed=False) — платёжный календарь и прогноз остатка уже читают
неподтверждённые операции, доп. код для их отображения не нужен.
"""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.models import RecurringFrequencyEnum, RecurringTemplate, Transaction

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _next_run_after(template: RecurringTemplate, after: date) -> date:
    if template.frequency == RecurringFrequencyEnum.weekly:
        days_ahead = (template.day_of_week - after.weekday()) % 7
        return after + timedelta(days=days_ahead or 7)
    # monthly — day_of_month ограничен 1..28 на уровне схемы, всегда есть в любом месяце
    year, month = after.year, after.month
    month += 1
    if month > 12:
        month = 1
        year += 1
    return date(year, month, template.day_of_month)


def generate_due_recurring(db) -> int:
    """Создаёт плановые операции для всех активных шаблонов с
    next_run_date <= today, сдвигает next_run_date на следующий период.
    Возвращает количество созданных операций — используется и джобом, и
    тестами (прямой вызов, без реального ожидания таймера)."""
    today = date.today()
    templates = (
        db.query(RecurringTemplate)
        .filter(RecurringTemplate.is_active.is_(True), RecurringTemplate.next_run_date <= today)
        .all()
    )
    created = 0
    for template in templates:
        db.add(
            Transaction(
                company_id=template.company_id,
                date_odds=template.next_run_date,
                account_id=template.account_id,
                category_id=template.category_id,
                project_id=template.project_id,
                counterparty_id=template.counterparty_id,
                type=template.type,
                amount=template.amount_rub,
                currency="RUB",
                amount_rub=template.amount_rub,
                comment=template.comment,
                payment_confirmed=False,
                accrual_confirmed=False,
                created_by=template.created_by,
            )
        )
        template.next_run_date = _next_run_after(template, template.next_run_date)
        created += 1
    db.commit()
    return created


def _run_job() -> None:
    db = SessionLocal()
    try:
        created = generate_due_recurring(db)
        if created:
            logger.info("recurring: создано %s плановых операций", created)
    finally:
        db.close()


def start_scheduler() -> None:
    """Регистрируется в main.py только при ENV=production или явном флаге
    RUN_SCHEDULER=1 — чтобы uvicorn --reload в dev не плодил по джобу на
    каждый релоуд (см. main.py)."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_run_job, "cron", hour=6, id="recurring_transactions")
    _scheduler.start()
