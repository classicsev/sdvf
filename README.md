# Финансовый учёт — стартовый проект

Замена связки 4 Excel-файлов (Архив / Внесение / Аналитика / Зарплатная ведомость) на
единое веб-приложение для управленческого учёта малого бизнеса.

## Стек

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic
- **DB**: PostgreSQL 16
- **Cache/queue**: Redis (для будущих банковских синков)
- **Frontend**: Next.js (React) — см. `prototype/finance_prototype.jsx` как эталон дизайна/функционала
- **Hosting**: Timeweb Cloud, сервер с соответствием 152-ФЗ (в системе хранятся банковские
  реквизиты сотрудников — персональные данные должны обрабатываться на серверах в РФ)
- **Экспорт**: openpyxl (backend) / SheetJS (frontend)

## Роли и права доступа

| Раздел | admin | operator | payroll_operator | project_manager | viewer |
|---|---|---|---|---|---|
| Операции | CRUD все | CRUD (ред. своих) | нет | чтение своего проекта | чтение |
| Дашборд/отчёты | всё | всё | нет | свой проект | всё (ro) |
| Зарплата | CRUD | нет | CRUD | нет | сводка без ФИО |
| Справочники | CRUD | чтение | чтение (сотрудники) | чтение своего проекта | чтение |
| Автоматизация (правила/интеграции) | CRUD | нет | нет | нет | нет |
| API-ключи | CRUD | нет | нет | нет | нет |
| Аудит-лог | всё | нет | только «Зарплата» | нет | нет |
| Пользователи | CRUD | нет | нет | нет | нет |

Важно: `project_manager` должен видеть только свои данные через **row-level security на
бэкенде** (фильтр по `project_id` из токена, а не из query-параметра запроса).

## Схема БД (см. `backend/app/models.py` для полной реализации)

Справочники: `accounts`, `categories`, `projects`, `counterparties`, `employees`, `users`
Транзакции: `transactions`, `planning`, `payroll_accruals`, `payroll_payments`
Автоматизация/аудит: `automation_rules`, `integrations`, `audit_log`
Курсы: `exchange_rates`

Денежные суммы — только `Numeric`, никогда `Float` (важно для точности копеек).
`transactions.amount_rub` фиксируется на дату операции по курсу на тот момент —
не пересчитывается задним числом.

## API-эндпоинты (см. `backend/app/routers/`)

```
POST   /auth/login              GET /auth/me
GET|POST|PATCH|DELETE /transactions            GET /transactions/export.xlsx
GET    /reports/dashboard-summary
GET    /reports/cashflow | /pnl | /balance | /debt | /profitability | /payment-calendar
GET|POST /employees, /payroll/accruals, /payroll/payments
GET|POST|PATCH|DELETE /categories | /projects | /accounts | /counterparties
GET|POST|PATCH|DELETE /automation-rules
GET /integrations   POST /integrations/:id/connect|disconnect
GET /audit-log
GET|POST|PATCH|DELETE /users
```

## Roadmap

0. Подготовка окружения — 1 нед.
1. MVP: операции + дашборд + роли + мультивалюта + экспорт — 4-6 нед.
2. Отчётность: календарь/ОПУ/баланс/задолженность/рентабельность/аудит — 2-3 нед.
3. Зарплата — 2-3 нед. (параллельно с 2)
4. Автоматизация правил + открытый API — 3-4 нед.
5. Интеграции: Т-Банк, Альфа-Банк, Wildberries, Ozon, 1С, amoCRM — 4-8 нед., по одной
6. Мобильное приложение — PWA поверх готового Next.js фронтенда — 2-3 нед.

## С чего начать в Claude Code

1. `cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
2. Поднять Postgres/Redis: `docker compose up -d db redis`
3. `alembic upgrade head` (после того как будут написаны первые миграции из `models.py`)
4. `uvicorn app.main:app --reload`
5. Для фронтенда: `npx create-next-app@latest frontend` (или адаптировать `prototype/finance_prototype.jsx` внутрь него) и перенести компоненты из прототипа
6. Реализовать эндпоинты из `backend/app/routers/` по одному, по порядку roadmap (этап 1 → 6)

`prototype/finance_prototype.jsx` — рабочий React-прототип с демо-данными: полный референс
по функциональности и дизайну (7 экранов, все отчёты, роли, стили, полный add/edit/delete
для справочников — статьи, проекты, счета, контрагенты, сотрудники). Использовать как
источник вёрстки/логики при переносе на Next.js + реальный API.

Backend: `POST/PATCH/DELETE` для `/categories`, `/projects`, `/accounts`, `/counterparties`
и `/payroll/employees` уже реализованы по-настоящему (не заглушки) — можно сразу подключать
фронтенд-формы из прототипа к этим эндпоинтам. Оставшиеся TODO в коде: бизнес-правило на
удаление записей, у которых уже есть связанные transactions/начисления (сейчас удаление
физическое — предложить деактивацию `is_active=False` вместо DELETE, где это уместно).

## Тесты

Backend покрыт pytest-тестами на самую рискованную логику: права доступа и RLS,
конвертация валют, движок правил автоматизации, шифрование ПДн, серверный расчёт сумм
в зарплате, математика отчётов. Тесты используют отдельную БД `finance_test_db`
(в том же Postgres) — dev-данные не трогают.

```bash
cd backend && source venv/bin/activate
docker exec finance-app-starter-db-1 psql -U finance -d finance_db -c "CREATE DATABASE finance_test_db OWNER finance"  # один раз
python -m pytest                              # запуск
python -m pytest --cov=app --cov-report=term-missing  # с покрытием
```
