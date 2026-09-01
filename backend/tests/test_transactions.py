import datetime

import openpyxl

from app.models import ExchangeRate, RoleEnum, Transaction, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_project, make_project_group, make_user


def test_create_transaction_rub_no_conversion(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.income)

    resp = client.post(
        "/transactions",
        headers=auth_headers(admin),
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 1000,
            "currency": "RUB",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["amount_rub"] == 1000.0


def test_update_transaction_with_date_odds_in_payload_does_not_crash_audit_log(client, db_session):
    """Регрессия: log_action писал payload.model_dump(exclude_unset=True) как
    есть в JSONB-колонку — если фронт присылает date_odds (а он присылает
    его всегда, даже когда дата не менялась, вместе с остальными полями
    формы), это объект datetime.date, а не строка, и драйвер падал с
    "Object of type date is not JSON serializable" — реальный сбой на
    проде при обычном редактировании операции (смена статьи+контрагента)."""
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.expense)
    other_category = make_category(db_session, name="Другая статья", tx_type=TxTypeEnum.expense)

    created = client.post(
        "/transactions",
        headers=auth_headers(admin),
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "expense",
            "amount": 100,
            "currency": "RUB",
        },
    ).json()

    resp = client.patch(
        f"/transactions/{created['id']}",
        headers=auth_headers(admin),
        json={"date_odds": "2026-06-01", "category_id": other_category.id, "amount": 225091},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["category_id"] == other_category.id


def test_bank_payment_purpose_and_comment_are_independent_fields(client, db_session):
    """Назначение платежа из банка (bank_payment_purpose) и собственная
    заметка пользователя (comment) — разные поля, правка одного не должна
    затирать другое."""
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.expense)

    created = client.post(
        "/transactions",
        headers=auth_headers(admin),
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "expense",
            "amount": 100,
            "currency": "RUB",
            "bank_payment_purpose": "Оплата по счёту №71 от 20.08.2026",
        },
    ).json()
    assert created["bank_payment_purpose"] == "Оплата по счёту №71 от 20.08.2026"
    assert created["comment"] is None

    resp = client.patch(
        f"/transactions/{created['id']}",
        headers=auth_headers(admin),
        json={"comment": "уточнить у бухгалтера"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["comment"] == "уточнить у бухгалтера"
    assert body["bank_payment_purpose"] == "Оплата по счёту №71 от 20.08.2026"


def test_create_transaction_foreign_currency_without_rate_fails(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, currency="USD")
    category = make_category(db_session, tx_type=TxTypeEnum.expense)

    resp = client.post(
        "/transactions",
        headers=auth_headers(admin),
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "expense",
            "amount": 100,
            "currency": "USD",
        },
    )
    assert resp.status_code == 422
    assert "курса" in resp.json()["detail"]


def test_create_transaction_foreign_currency_uses_latest_rate_not_future(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session, currency="USD")
    category = make_category(db_session, tx_type=TxTypeEnum.income)

    db_session.add(ExchangeRate(currency="USD", rate_to_rub=80, date=datetime.date(2026, 6, 1)))
    # Курс "из будущего" относительно операции — не должен использоваться
    db_session.add(ExchangeRate(currency="USD", rate_to_rub=999, date=datetime.date(2026, 6, 20)))
    db_session.commit()

    resp = client.post(
        "/transactions",
        headers=auth_headers(admin),
        json={
            "date_odds": "2026-06-05",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 10,
            "currency": "USD",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["amount_rub"] == 800.0  # 10 * 80, курс на 06-01, не 999


def test_operator_can_only_edit_own_transaction(client, db_session):
    op1 = make_user(db_session, RoleEnum.operator, email="op1@test.local")
    op2 = make_user(db_session, RoleEnum.operator, email="op2@test.local")
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.expense)

    created = client.post(
        "/transactions",
        headers=auth_headers(op1),
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "expense",
            "amount": 500,
            "currency": "RUB",
        },
    ).json()

    resp = client.patch(
        f"/transactions/{created['id']}",
        headers=auth_headers(op2),
        json={"amount": 999},
    )
    assert resp.status_code == 403

    resp = client.patch(
        f"/transactions/{created['id']}",
        headers=auth_headers(op1),
        json={"amount": 999},
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == 999.0


def test_project_manager_cannot_see_other_project_transactions(client, db_session):
    project_a = make_project(db_session, "Проект A")
    project_b = make_project(db_session, "Проект Б")
    pm = make_user(db_session, RoleEnum.project_manager, project_id=project_a.id)
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.income)

    for project in (project_a, project_b):
        client.post(
            "/transactions",
            headers=auth_headers(admin),
            json={
                "date_odds": "2026-06-01",
                "account_id": account.id,
                "category_id": category.id,
                "project_id": project.id,
                "type": "income",
                "amount": 100,
                "currency": "RUB",
            },
        )

    resp = client.get("/transactions", headers=auth_headers(pm))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["project_id"] == project_a.id

    # project_manager не может обойти RLS через query-параметр
    resp = client.get(f"/transactions?project={project_b.id}", headers=auth_headers(pm))
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["project_id"] == project_a.id


def test_malformed_uuid_returns_404_not_500(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.patch(
        "/transactions/not-a-uuid",
        headers=auth_headers(admin),
        json={"amount": 1},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Операция не найдена"

    resp = client.delete("/transactions/not-a-uuid", headers=auth_headers(admin))
    assert resp.status_code == 404


def test_list_filters_by_account_category_and_date_range(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account_a = make_account(db_session, "Счёт А")
    account_b = make_account(db_session, "Счёт Б")
    category = make_category(db_session, tx_type=TxTypeEnum.income)

    def _tx(account_id, date_odds):
        return client.post(
            "/transactions",
            headers=headers,
            json={
                "date_odds": date_odds,
                "account_id": account_id,
                "category_id": category.id,
                "type": "income",
                "amount": 100,
                "currency": "RUB",
            },
        ).json()

    _tx(account_a.id, "2026-06-01")
    _tx(account_b.id, "2026-06-15")
    _tx(account_a.id, "2026-07-01")

    resp = client.get(f"/transactions?account={account_a.id}", headers=headers)
    assert len(resp.json()) == 2

    resp = client.get(f"/transactions?account={account_a.id}&date_from=2026-06-20", headers=headers)
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["date_odds"] == "2026-07-01"

    resp = client.get(f"/transactions?category={category.id}&date_to=2026-06-10", headers=headers)
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["account_id"] == account_a.id


def test_count_transactions_respects_same_filters(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account_a = make_account(db_session, "Счёт А")
    account_b = make_account(db_session, "Счёт Б")
    category = make_category(db_session, tx_type=TxTypeEnum.income)

    def _tx(account_id, date_odds):
        return client.post(
            "/transactions",
            headers=headers,
            json={
                "date_odds": date_odds,
                "account_id": account_id,
                "category_id": category.id,
                "type": "income",
                "amount": 100,
                "currency": "RUB",
            },
        ).json()

    _tx(account_a.id, "2026-06-01")
    _tx(account_b.id, "2026-06-15")
    _tx(account_a.id, "2026-07-01")

    resp = client.get("/transactions/count", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == 3

    resp = client.get(f"/transactions/count?account={account_a.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == 2

    resp = client.get(f"/transactions/count?account={account_a.id}&date_from=2026-06-20", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == 1


def test_list_filters_by_project_group(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.income)
    group_a = make_project_group(db_session, "Группа А")
    group_b = make_project_group(db_session, "Группа Б")
    project_a1 = make_project(db_session, "Проект А1", group_id=group_a.id)
    project_a2 = make_project(db_session, "Проект А2", group_id=group_a.id)
    project_b1 = make_project(db_session, "Проект Б1", group_id=group_b.id)
    project_none = make_project(db_session, "Без группы")

    def _tx(project_id, amount):
        return client.post(
            "/transactions",
            headers=headers,
            json={
                "date_odds": "2026-06-01",
                "account_id": account.id,
                "category_id": category.id,
                "project_id": project_id,
                "type": "income",
                "amount": amount,
                "currency": "RUB",
            },
        ).json()

    _tx(project_a1.id, 100)
    _tx(project_a2.id, 200)
    _tx(project_b1.id, 300)
    _tx(project_none.id, 400)

    resp = client.get(f"/transactions?project_group_id={group_a.id}", headers=headers)
    rows = resp.json()
    assert {r["amount"] for r in rows} == {100.0, 200.0}

    resp = client.get(f"/transactions/count?project_group_id={group_a.id}", headers=headers)
    assert resp.json() == 2

    # Явно выбранный project имеет приоритет над project_group_id.
    resp = client.get(
        f"/transactions?project_group_id={group_a.id}&project={project_b1.id}", headers=headers
    )
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["amount"] == 300.0


def test_list_filters_by_confirmed_status(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.income)

    def _tx(amount, payment_confirmed, accrual_confirmed):
        return client.post(
            "/transactions",
            headers=headers,
            json={
                "date_odds": "2026-06-01",
                "account_id": account.id,
                "category_id": category.id,
                "type": "income",
                "amount": amount,
                "currency": "RUB",
                "payment_confirmed": payment_confirmed,
                "accrual_confirmed": accrual_confirmed,
            },
        ).json()

    _tx(100, True, True)
    _tx(200, False, True)
    _tx(300, True, False)

    resp = client.get("/transactions?confirmed=confirmed", headers=headers)
    rows = resp.json()
    assert {r["amount"] for r in rows} == {100.0}

    resp = client.get("/transactions?confirmed=unconfirmed", headers=headers)
    rows = resp.json()
    assert {r["amount"] for r in rows} == {200.0, 300.0}

    resp = client.get("/transactions/count?confirmed=unconfirmed", headers=headers)
    assert resp.json() == 2


def test_close_month_uses_accrual_confirmed_not_date_opu_null(client, db_session):
    """Регрессия: с тех пор как форма операции стала сама подставлять
    сегодняшнюю дату начисления по умолчанию, date_opu у новых операций
    почти никогда не NULL — закрытие месяца больше не может опираться на
    date_opu.is_(None) и должно смотреть на accrual_confirmed."""
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.income)

    def _tx(date_opu, accrual_confirmed):
        return client.post(
            "/transactions",
            headers=headers,
            json={
                "date_odds": "2026-06-15",
                "date_opu": date_opu,
                "account_id": account.id,
                "category_id": category.id,
                "type": "income",
                "amount": 100,
                "currency": "RUB",
                "accrual_confirmed": accrual_confirmed,
            },
        ).json()

    # Как форма создаёт операции сейчас: date_opu всегда заполнена (сегодня
    # или дата оплаты), но accrual_confirmed может быть False — именно это
    # должно ловить закрытие месяца.
    unconfirmed = _tx("2026-06-20", False)
    confirmed = _tx("2026-06-25", True)
    legacy_null = _tx(None, False)

    resp = client.post(
        "/transactions/close-month",
        headers=headers,
        json={"company_id": account.company_id, "month": "2026-06-01"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 2

    db_session.expire_all()

    def _get(tx_id):
        return db_session.get(Transaction, tx_id)

    got = _get(unconfirmed["id"])
    assert got.date_opu.isoformat() == "2026-06-01"
    assert got.accrual_confirmed is True

    got = _get(confirmed["id"])
    assert got.date_opu.isoformat() == "2026-06-25"  # подтверждённую дату не трогаем

    got = _get(legacy_null["id"])
    assert got.date_opu.isoformat() == "2026-06-01"
    assert got.accrual_confirmed is True


def test_export_xlsx_returns_valid_workbook_with_readable_names(client, db_session, tmp_path):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, "Расчётный счёт")
    category = make_category(db_session, "Аренда офиса", TxTypeEnum.expense)

    client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "expense",
            "amount": 15000,
            "currency": "RUB",
            "comment": "Июнь",
        },
    )

    resp = client.get("/transactions/export.xlsx", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    xlsx_path = tmp_path / "export.xlsx"
    xlsx_path.write_bytes(resp.content)
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][0] == "Дата операции"
    data_row = rows[1]
    assert data_row[3] == "Расчётный счёт"  # счёт по имени, не ID
    assert data_row[4] == "Аренда офиса"  # статья по имени
    assert data_row[9] == 15000  # сумма в руб.


def test_locked_period_blocks_create_update_delete(client, db_session):
    from app.models import Company

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session, tx_type=TxTypeEnum.income)

    company = db_session.get(Company, account.company_id)
    company.locked_before_date = datetime.date(2026, 6, 15)
    db_session.commit()

    # Создание операции ВНУТРИ закрытого периода — 403.
    resp = client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": "2026-06-10",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 100,
            "currency": "RUB",
        },
    )
    assert resp.status_code == 403, resp.text

    # Создание операции ПОСЛЕ закрытого периода — ок.
    ok = client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": "2026-06-20",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 100,
            "currency": "RUB",
        },
    ).json()

    # Правка операции после закрытого периода — ок, пока не переносишь дату внутрь него.
    resp = client.patch(f"/transactions/{ok['id']}", headers=headers, json={"amount": 200})
    assert resp.status_code == 200, resp.text

    # Перенос даты операции ВНУТРЬ закрытого периода — 403.
    resp = client.patch(f"/transactions/{ok['id']}", headers=headers, json={"date_odds": "2026-06-05"})
    assert resp.status_code == 403, resp.text

    # Удаление операции после закрытого периода — ок.
    resp = client.delete(f"/transactions/{ok['id']}", headers=headers)
    assert resp.status_code == 200, resp.text

    # Создаём операцию НАПРЯМУЮ в БД (как это делает банковский синк — минуя
    # роутер) с датой внутри "закрытого" периода, затем убеждаемся, что
    # ПРАВКА/УДАЛЕНИЕ через обычный API для неё блокируются.
    old_tx = Transaction(
        company_id=account.company_id,
        date_odds=datetime.date(2026, 6, 1),
        account_id=account.id,
        category_id=category.id,
        type=TxTypeEnum.income,
        amount=50,
        currency="RUB",
        amount_rub=50,
        created_by=admin.id,
    )
    db_session.add(old_tx)
    db_session.commit()

    resp = client.patch(f"/transactions/{old_tx.id}", headers=headers, json={"amount": 999})
    assert resp.status_code == 403, resp.text
    resp = client.delete(f"/transactions/{old_tx.id}", headers=headers)
    assert resp.status_code == 403, resp.text


def test_company_modules_update_accepts_period_lock_and_accrual_toggle(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.patch(
        "/companies/me/modules",
        headers=headers,
        json={"show_accrual_date_field": False, "locked_before_date": "2026-07-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["show_accrual_date_field"] is False
    assert body["locked_before_date"] == "2026-07-31"

    # Снятие блокировки — явный null.
    resp = client.patch(
        "/companies/me/modules", headers=headers, json={"locked_before_date": None}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["locked_before_date"] is None
