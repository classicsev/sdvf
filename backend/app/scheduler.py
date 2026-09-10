"""Фоновые джобы проекта — APScheduler в процессе backend, не Celery+beat:
однопроцессный uvicorn на одном сервере, нагрузка по расписанию мизерная,
отдельный worker+beat контейнер ради пары задач избыточен.

1. Повторяющиеся плановые операции — создаёт обычную Transaction
   (payment_confirmed=False, accrual_confirmed=False); платёжный календарь
   и прогноз остатка уже читают неподтверждённые операции, доп. код для их
   отображения не нужен.
2. Автосинк Google-таблицы склада (добавлено 2026-09-10) — раньше синк
   запускался ТОЛЬКО кнопкой "Синхронизировать сейчас", из-за чего реальные
   правки в таблице могли неделями не попадать в приложение незаметно (см.
   HANDOVER.md). Джоб не создаёт новых операций, просто регулярно вызывает
   тот же sync_connection, что и кнопка — конкретный интервал реального
   похода в Google по-прежнему решает connection.autosync_interval_minutes,
   джоб просто гарантирует, что этот интервал реально проверяется, даже
   если никто не открывает страницу Склада.
"""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.models import RecurringFrequencyEnum, RecurringTemplate, Transaction, WarehouseSheetConnection

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


def sync_all_warehouse_sheets(db) -> int:
    """Проходит по ВСЕМ подключённым Google-таблицам склада (across всех
    компаний — фоновый джоб не привязан к конкретному пользователю/его
    правам доступа, в отличие от HTTP-эндпоинта /warehouse/sheets/sync-all)
    и синкает каждую через тот же sync_connection, что и кнопка
    "Синхронизировать сейчас". force=False — реальный поход в Google
    по-прежнему ограничен connection.autosync_interval_minutes, джоб просто
    даёт этому таймеру шанс сработать без участия пользователя. Возвращает
    число реально обработанных (не пропущенных по таймеру) подключений."""
    from app.routers.warehouse_sync import sync_connection  # локальный импорт — избегаем цикла при старте приложения

    connections = db.query(WarehouseSheetConnection).filter(WarehouseSheetConnection.is_connected.is_(True)).all()
    processed = 0
    for conn in connections:
        try:
            was_processed, _results = sync_connection(db, conn, force=False)
            if was_processed:
                processed += 1
        except Exception:
            logger.exception("warehouse_sheets: сбой автосинка подключения %s", conn.id)
    return processed


def _run_warehouse_sheets_job() -> None:
    db = SessionLocal()
    try:
        processed = sync_all_warehouse_sheets(db)
        if processed:
            logger.info("warehouse_sheets: автосинк обработал %s подключений", processed)
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
    # Каждый час — реальный поход в Google Sheets всё равно ограничен
    # autosync_interval_minutes на каждом подключении (обычно 180 мин),
    # часовой интервал джоба просто даёт этому таймеру шанс сработать.
    _scheduler.add_job(_run_warehouse_sheets_job, "cron", minute=15, id="warehouse_sheets_autosync")
    _scheduler.start()
