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

| Раздел | admin | operator | payroll_operator | project_manager | viewer | warehouse_operator |
|---|---|---|---|---|---|---|
| Операции | CRUD все | CRUD (ред. своих) | нет | чтение своего проекта | чтение | нет |
| Дашборд/отчёты | всё | всё | нет | свой проект | всё (ro) | нет |
| Зарплата | CRUD | нет | CRUD | нет | сводка без ФИО | нет |
| Справочники | CRUD | чтение | чтение (сотрудники) | чтение своего проекта | чтение | нет |
| Автоматизация (правила/интеграции) | CRUD | нет | нет | нет | нет | нет |
| API-ключи | CRUD | нет | нет | нет | нет | нет |
| Склад (остатки/движения/справочники) | CRUD | нет | нет | нет | чтение | CRUD |
| Аудит-лог | всё | нет | только «Зарплата» | нет | нет | нет |
| Пользователи | CRUD | нет | нет | нет | нет | нет |

Важно: `project_manager` должен видеть только свои данные через **row-level security на
бэкенде** (фильтр по `project_id` из токена, а не из query-параметра запроса).

## Схема БД (см. `backend/app/models.py` для полной реализации)

Справочники: `accounts`, `categories`, `projects`, `counterparties`, `employees`, `users`
Транзакции: `transactions`, `planning`, `payroll_accruals`, `payroll_payments`
Автоматизация/аудит: `automation_rules`, `integrations`, `audit_log`
Курсы: `exchange_rates`
Склад (Этап «Склад-1» — см. `backend/app/routers/warehouse.py`): `warehouses`, `products`,
`product_variants` (калибр/модификация товара), `stock_movements` (единая лента движений
с полем `direction`, остаток считается на лету суммой по ленте, а не хранится отдельно).
Мост с зарплатой: `stock_movements.executor_id`/`payroll_rate` → авто-создание
`payroll_accruals` при приходе товара.
Заказы (Этап «Склад-2» — см. `backend/app/routers/orders.py`): `orders`/`order_lines`.
Резерв — заказ в статусе `reserved` (без отдельной таблицы), доступно-к-обещанию считается
в `/warehouse/balances` вычитанием суммы резервов из остатка. Отгрузка (`/orders/:id/ship`)
создаёт `stock_movements` (`direction=out`, `order_id` → заказ) автоматически.
Производство (Этап «Склад-3» — см. `backend/app/routers/production.py`): `production_recipes`
(техкарта: один выходной вариант) / `production_recipe_inputs` (норма расхода сырья на 1 ед.
выхода) / `production_runs`. Партия производства (`POST /production/runs`) автоматически
создаёт `stock_movements` — расход каждого компонента сырья (`production_consume`) по норме
из техкарты и приход готового продукта (`production_yield`), связанные через
`production_run_id`.
amoCRM (Этап «Склад-4» — см. `backend/app/integrations/amocrm.py`, `backend/app/routers/
automation.py::sync_amocrm`): в отличие от Т-Банка, у amoCRM нет статичного токена для
внешних интеграций — только OAuth2 (client_id/secret + access/refresh token), поэтому
подключение и синк — отдельные эндпоинты `connect-amocrm`/`sync-amocrm`, а не общие
`connect`/`sync`. Синк переносит: контакты → `counterparties` (дедуп по имени), сделки в
статусе «Успешно реализовано» (`status_id=142`, зарезервированный ID во всех аккаунтах
amoCRM) → доходные `transactions`. **Важно**: если доход уже приходит через банковский
синк (Т-Банк/Альфа), синк сделок amoCRM может задвоить выручку — включать оба синка
одновременно для одних и тех же поступлений не стоит без сверки. Клиент троттлит запросы
между страницами (лимит amoCRM ~7 запросов/сек) и имеет потолок в `MAX_PAGES` страниц —
защита от зацикливания пагинации.

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
GET /integrations   POST /integrations/:id/connect|disconnect|sync
POST /integrations/:id/connect-amocrm|sync-amocrm   (отдельно — у amoCRM OAuth2, не статичный токен)
GET /audit-log
GET|POST|PATCH|DELETE /users
GET|POST|DELETE /api-keys       (заголовок X-API-Key — альтернатива JWT для внешних систем)
GET|POST|PATCH|DELETE /warehouse/warehouses | /warehouse/products | /warehouse/variants
GET|POST|DELETE /warehouse/movements   POST /warehouse/movements/transfer
GET /warehouse/balances   GET /warehouse/employees (только имя, без реквизитов)
GET|POST|PATCH|DELETE /orders   POST|DELETE /orders/:id/lines
POST /orders/:id/reserve | /orders/:id/cancel | /orders/:id/ship
GET|POST|PATCH|DELETE /production/recipes
GET|POST|DELETE /production/runs
```

## Roadmap

0. Подготовка окружения — 1 нед.
1. MVP: операции + дашборд + роли + мультивалюта + экспорт — 4-6 нед.
2. Отчётность: календарь/ОПУ/баланс/задолженность/рентабельность/аудит — 2-3 нед.
3. Зарплата — 2-3 нед. (параллельно с 2)
4. Автоматизация правил + открытый API — 3-4 нед.
5. Интеграции: Т-Банк, Альфа-Банк, Wildberries, Ozon, 1С, amoCRM — 4-8 нед., по одной
6. Мобильное приложение — PWA поверх готового Next.js фронтенда — 2-3 нед. **Готово**:
   `frontend/public/manifest.json` + `frontend/public/sw.js` + `frontend/components/
   ServiceWorkerRegister.jsx` — устанавливается на экран как приложение (Android/desktop
   Chrome — автоматически, iOS Safari — вручную через «Поделиться» → «На экран
   «Домой»»). Service worker кэширует только неизменяемую статику сборки
   (`_next/static`, иконки) — HTML-навигация и все запросы к API всегда идут в сеть
   напрямую, без кэша: устаревшие финансовые/складские данные офлайн опаснее, чем их
   отсутствие. Подготовка к нативной версии: путь к API вынесен в
   `NEXT_PUBLIC_API_BASE_URL` (не хардкожен), сам SW ни на что в React-коде не влияет
   (чисто аддитивный слой) — при переходе на нативное приложение позже предполагается
   Capacitor (оборачивает тот же Next.js/PWA билд в нативную оболочку для App
   Store/Google Play) поверх уже готового фронтенда, без переписывания UI.

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
Postgres/Redis/backend/frontend не публикуют порты наружу — наружу смотрит только сервис
`caddy` (80/443). **Проверено вживую в проде** (не только по документации): сервер Timeweb
Cloud (Ubuntu 24.04), домен `uvost.ru` + `api.uvost.ru`, сборка образов, миграции на чистой
БД, HTTPS-сертификаты Let's Encrypt получены и провалидированы, логин и запросы между
контейнерами по внутренней docker-сети — всё через реальный домен, не localhost.

HTTPS настроен через `caddy:2-alpine` (сервис `caddy` в compose + `Caddyfile` в корне
репозитория) — автоматически получает и продлевает бесплатные сертификаты Let's Encrypt,
отдельно certbot/Nginx настраивать не нужно. `Caddyfile` — два простых блока
`reverse_proxy` (фронтенд/бекенд по внутренним docker-именам `frontend:3000` /
`backend:8000`).

### Шаги

1. Скопировать `backend/.env.example` → `backend/.env`, заполнить **свежесгенерированными**
   секретами (команды генерации — прямо в комментариях файла), указать
   `CORS_ORIGINS=https://ваш-домен` (реальный домен фронтенда, не localhost).
2. Скопировать `.env.prod.example` → `.env` (в корне проекта), задать `POSTGRES_PASSWORD`,
   `REDIS_PASSWORD` и `NEXT_PUBLIC_API_BASE_URL=https://api.ваш-домен`. **`POSTGRES_PASSWORD`
   здесь должен совпадать с паролем внутри `DATABASE_URL` в `backend/.env`** — Postgres
   применяет `POSTGRES_PASSWORD` только при первой инициализации пустого volume, дальше эта
   переменная игнорируется. Помнить: `NEXT_PUBLIC_API_BASE_URL` встраивается в JS на этапе
   `build`, при изменении нужен пересобранный образ фронтенда, простого рестарта мало.
3. Отредактировать `Caddyfile` — вписать свои домены вместо `uvost.ru`/`api.uvost.ru`.
4. DNS: A-записи домена и поддомена `api.*` должны указывать на IP сервера **до** запуска
   Caddy — иначе Let's Encrypt не сможет подтвердить владение доменом. Публичный IPv4 у
   Timeweb Cloud — платная опция, добавляется отдельно при заказе сервера.
5. `docker compose -f docker-compose.prod.yml up -d --build`
6. Накатить миграции (не делается автоматически): `docker compose -f docker-compose.prod.yml exec backend alembic upgrade head`
7. Создать первого администратора (самостоятельная регистрация не предусмотрена —
   `POST /users` защищён ролью admin):
   ```bash
   docker compose -f docker-compose.prod.yml exec backend python scripts/create_admin.py \
     --email admin@example.ru --full-name "Имя Фамилия" --password "сгенерировать_сильный_пароль"
   ```
8. Проверить `docker logs <контейнер-caddy>` — там видно, получил ли Caddy сертификаты
   (`certificate obtained successfully` на оба домена).

### Чек-лист перед реальным запуском

- [x] `JWT_SECRET_KEY` и `FIELD_ENCRYPTION_KEY` — свежесгенерированные, отличные от dev-версий
- [x] `CORS_ORIGINS` указывает только на реальный домен, без localhost
- [x] HTTPS обязателен — Caddy + Let's Encrypt, автопродление
- [x] Пароли Postgres/Redis не совпадают с dev-значениями из этого репозитория
- [x] `backend/.env` и корневой `.env` не закоммичены (уже в `.gitignore`)
- [x] Firewall (`ufw`): открыты только 22 (SSH)/80/443, остальное закрыто; backend/frontend
      без публикации портов наружу — доступ только через Caddy по внутренней сети

### 152-ФЗ — что закрыто технически, а что нет

Технически: сервер физически в РФ (Timeweb Cloud подходит), банковские реквизиты
сотрудников шифруются на уровне приложения (`FIELD_ENCRYPTION_KEY`, см. `app/crypto.py`).
Но 152-ФЗ — это не только код: регистрация в реестре операторов персональных данных
(Роскомнадзор), политика обработки ПДн, согласия сотрудников — организационно-юридические
шаги вне зоны того, что можно решить в репозитории.
