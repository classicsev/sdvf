import datetime

import openpyxl

from app.models import ExchangeRate, RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_project, make_user


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
