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

CI (`.github/workflows/ci.yml`) гоняет тот же набор тестов и продакшен-сборку фронтенда
при каждом push/PR — активируется автоматически после первого `git push` в GitHub.

## Деплой

`docker-compose.prod.yml` — прод-вариант стека: без hot-reload и volume-монтирования кода
(код запечён в образ), фронтенд собирается как Next.js `standalone`-сервер (не dev-режим),
Postgres/Redis не публикуют порты наружу. Проверено вживую: сборка обоих образов, миграции
на чистой БД, логин, запросы между контейнерами по внутренней сети — реальным прогоном,
не только по документации.

### Шаги

1. Скопировать `backend/.env.example` → `backend/.env`, заполнить **свежесгенерированными**
   секретами (команды генерации — прямо в комментариях файла), указать
   `CORS_ORIGINS=https://ваш-домен` (реальный домен фронтенда, не localhost).
2. Скопировать `.env.prod.example` → `.env` (в корне проекта), задать `POSTGRES_PASSWORD`,
   `REDIS_PASSWORD` и `NEXT_PUBLIC_API_BASE_URL`. **`POSTGRES_PASSWORD` здесь должен
   совпадать с паролем внутри `DATABASE_URL` в `backend/.env`** — Postgres применяет
   `POSTGRES_PASSWORD` только при первой инициализации пустого volume, дальше эта
   переменная игнорируется.
3. `docker compose -f docker-compose.prod.yml up -d --build`
4. Накатить миграции (не делается автоматически): `docker compose -f docker-compose.prod.yml exec backend alembic upgrade head`
5. Создать первого администратора (самостоятельная регистрация не предусмотрена —
   `POST /users` защищён ролью admin):
   ```bash
   docker compose -f docker-compose.prod.yml exec backend python scripts/create_admin.py \
     --email admin@example.ru --full-name "Имя Фамилия" --password "сгенерировать_сильный_пароль"
   ```
6. Поставить перед портами 8000 (backend) и 3000 (frontend) реверс-прокси с HTTPS
   (Nginx/Caddy/встроенный балансировщик Timeweb Cloud) — сам compose HTTPS не терминирует.

### Чек-лист перед реальным запуском

- [ ] `JWT_SECRET_KEY` и `FIELD_ENCRYPTION_KEY` — свежесгенерированные, отличные от dev-версий
- [ ] `CORS_ORIGINS` указывает только на реальный домен, без localhost
- [ ] HTTPS обязателен (реверс-прокси перед контейнерами)
- [ ] Пароли Postgres/Redis не совпадают с dev-значениями из этого репозитория
- [ ] `backend/.env` и корневой `.env` не закоммичены (уже в `.gitignore`)

### 152-ФЗ — что закрыто технически, а что нет

Технически: сервер физически в РФ (Timeweb Cloud подходит), банковские реквизиты
сотрудников шифруются на уровне приложения (`FIELD_ENCRYPTION_KEY`, см. `app/crypto.py`).
Но 152-ФЗ — это не только код: регистрация в реестре операторов персональных данных
(Роскомнадзор), политика обработки ПДн, согласия сотрудников — организационно-юридические
шаги вне зоны того, что можно решить в репозитории.
