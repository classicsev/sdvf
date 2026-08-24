"""Карточка проекта — /reports/projects/{id}/detail, бюджет проекта
(/projects/{id}/budget-lines), обновлённый /reports/profitability (весь
список + статус), и базовое покрытие project-groups (0 тестов было — см.
HANDOVER.md "Карточка проекта"). См. HANDOVER.md для полного описания."""

from app.models import RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_project, make_project_group, make_user


def _create_tx(client, headers, account_id, category_id, amount, tx_type, date_odds="2026-06-15", **extra):
    payload = {
        "date_odds": date_odds,
        "account_id": account_id,
        "category_id": category_id,
        "type": tx_type,
        "amount": amount,
        "currency": "RUB",
    }
    payload.update(extra)
    resp = client.post("/transactions", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# /reports/projects/{id}/detail
# ---------------------------------------------------------------------------


def test_project_detail_accrual_vs_cash_method_differ(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    project = make_project(db_session)
    income_cat = make_category(db_session, "Продажи", TxTypeEnum.income)

    # Начисление подтверждено (это выручка), оплата — нет (денег ещё не было).
    _create_tx(
        client, headers, account.id, income_cat.id, 1000, "income",
        project_id=project.id, payment_confirmed=False, accrual_confirmed=True,
    )

    accrual_resp = client.get(
        f"/reports/projects/{project.id}/detail", params={"method": "accrual"}, headers=headers
    ).json()
    cash_resp = client.get(
        f"/reports/projects/{project.id}/detail", params={"method": "cash"}, headers=headers
    ).json()

    assert accrual_resp["revenue"] == 1000.0
    assert cash_resp["revenue"] == 0.0


def test_project_detail_date_range_filters(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    project = make_project(db_session)
    income_cat = make_category(db_session, "Продажи", TxTypeEnum.income)

    _create_tx(client, headers, account.id, income_cat.id, 500, "income", project_id=project.id, date_odds="2026-01-10")
    _create_tx(client, headers, account.id, income_cat.id, 700, "income", project_id=project.id, date_odds="2026-06-10")

    resp = client.get(
        f"/reports/projects/{project.id}/detail",
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
        headers=headers,
    ).json()
    assert resp["revenue"] == 700.0

    resp_all = client.get(f"/reports/projects/{project.id}/detail", headers=headers).json()
    assert resp_all["revenue"] == 1200.0


def test_project_detail_status_transitions(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    project = make_project(db_session)
    expense_cat = make_category(db_session, "Расход", TxTypeEnum.expense)

    resp = client.get(f"/reports/projects/{project.id}/detail", headers=headers).json()
    assert resp["status"] == "planned"

    _create_tx(client, headers, account.id, expense_cat.id, 100, "expense", project_id=project.id)
    resp = client.get(f"/reports/projects/{project.id}/detail", headers=headers).json()
    assert resp["status"] == "in_progress"

    client.patch(f"/projects/{project.id}", headers=headers, json={"name": project.name, "is_active": False})
    resp = client.get(f"/reports/projects/{project.id}/detail", headers=headers).json()
    assert resp["status"] == "closed"


def test_project_detail_by_month_and_by_category(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    project = make_project(db_session)
    rent_cat = make_category(db_session, "Аренда", TxTypeEnum.expense, group_name="OPEX")
    ads_cat = make_category(db_session, "Реклама", TxTypeEnum.expense, group_name="OPEX")
    income_cat = make_category(db_session, "Продажи", TxTypeEnum.income)

    _create_tx(client, headers, account.id, income_cat.id, 1000, "income", project_id=project.id, date_odds="2026-05-01")
    _create_tx(client, headers, account.id, rent_cat.id, 200, "expense", project_id=project.id, date_odds="2026-05-01")
    _create_tx(client, headers, account.id, ads_cat.id, 50, "expense", project_id=project.id, date_odds="2026-06-01")

    resp = client.get(f"/reports/projects/{project.id}/detail", headers=headers).json()

    by_month = {row["period"]: row for row in resp["by_month"]}
    assert by_month["2026-05"]["revenue"] == 1000.0
    assert by_month["2026-05"]["expense"] == 200.0
    assert by_month["2026-06"]["expense"] == 50.0

    by_category_total = {row["category"]: row["amount"] for row in resp["by_category"]}
    assert by_category_total["OPEX"] == 250.0  # общая группа для Аренды и Рекламы


def test_project_detail_plan_source_operations_uses_unconfirmed_accrual(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    project = make_project(db_session)
    expense_cat = make_category(db_session, "Расход", TxTypeEnum.expense)

    _create_tx(
        client, headers, account.id, expense_cat.id, 300, "expense",
        project_id=project.id, accrual_confirmed=False,
    )

    resp = client.get(
        f"/reports/projects/{project.id}/detail", params={"plan_source": "operations"}, headers=headers
    ).json()
    assert resp["plan"]["expense"] == 300.0
    assert resp["expense"] == 0.0  # неподтверждённая операция не факт


def test_project_detail_plan_source_budget(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    project = make_project(db_session)
    expense_cat = make_category(db_session, "Расход", TxTypeEnum.expense)

    client.post(
        f"/projects/{project.id}/budget-lines",
        headers=headers,
        json=[{"category_id": expense_cat.id, "amount": 5000}],
    )

    resp = client.get(
        f"/reports/projects/{project.id}/detail", params={"plan_source": "budget"}, headers=headers
    ).json()
    assert resp["plan"]["expense"] == 5000.0


def test_project_detail_404_for_project_manager_other_project(client, db_session):
    from tests.conftest import make_project as _mp

    admin = make_user(db_session, RoleEnum.admin)
    project_a = _mp(db_session, "A")
    project_b = _mp(db_session, "B")
    pm = make_user(db_session, RoleEnum.project_manager, project_id=project_a.id)

    resp = client.get(f"/reports/projects/{project_b.id}/detail", headers=auth_headers(pm))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /reports/profitability — теперь весь список проектов (даже без операций),
# со статусом
# ---------------------------------------------------------------------------


def test_profitability_report_lists_project_with_zero_activity(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    project = make_project(db_session)

    resp = client.get("/reports/profitability", headers=headers)
    row = next(r for r in resp.json() if r["project_id"] == project.id)
    assert row["revenue"] == 0.0
    assert row["status"] == "planned"


def test_profitability_report_status_in_progress_and_closed(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    project = make_project(db_session)
    income_cat = make_category(db_session, "Продажи", TxTypeEnum.income)

    _create_tx(client, headers, account.id, income_cat.id, 100, "income", project_id=project.id)
    resp = client.get("/reports/profitability", headers=headers)
    row = next(r for r in resp.json() if r["project_id"] == project.id)
    assert row["status"] == "in_progress"

    client.patch(f"/projects/{project.id}", headers=headers, json={"name": project.name, "is_active": False})
    resp = client.get("/reports/profitability", headers=headers)
    row = next(r for r in resp.json() if r["project_id"] == project.id)
    assert row["status"] == "closed"


# ---------------------------------------------------------------------------
# /projects/{id}/budget-lines — CRUD, admin-only
# ---------------------------------------------------------------------------


def test_budget_lines_replace_upserts_and_removes_missing(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    project = make_project(db_session)
    cat_a = make_category(db_session, "Статья A", TxTypeEnum.expense)
    cat_b = make_category(db_session, "Статья Б", TxTypeEnum.expense)

    resp = client.post(
        f"/projects/{project.id}/budget-lines",
        headers=headers,
        json=[{"category_id": cat_a.id, "amount": 1000}, {"category_id": cat_b.id, "amount": 2000}],
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Второй вызов — только статья A с новой суммой, статья Б должна пропасть.
    resp = client.post(
        f"/projects/{project.id}/budget-lines",
        headers=headers,
        json=[{"category_id": cat_a.id, "amount": 1500}],
    )
    assert resp.status_code == 200
    lines = resp.json()
    assert len(lines) == 1
    assert lines[0]["category_id"] == cat_a.id
    assert lines[0]["amount"] == 1500.0


def test_budget_lines_requires_admin(client, db_session):
    operator = make_user(db_session, RoleEnum.operator)
    project = make_project(db_session)
    cat = make_category(db_session, tx_type=TxTypeEnum.expense)

    resp = client.post(
        f"/projects/{project.id}/budget-lines",
        headers=auth_headers(operator),
        json=[{"category_id": cat.id, "amount": 100}],
    )
    assert resp.status_code == 403


def test_delete_single_budget_line(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    project = make_project(db_session)
    cat = make_category(db_session, tx_type=TxTypeEnum.expense)

    created = client.post(
        f"/projects/{project.id}/budget-lines", headers=headers, json=[{"category_id": cat.id, "amount": 100}]
    ).json()
    line_id = created[0]["id"]

    resp = client.delete(f"/projects/{project.id}/budget-lines/{line_id}", headers=headers)
    assert resp.status_code == 200

    remaining = client.get(f"/projects/{project.id}/budget-lines", headers=headers).json()
    assert remaining == []


# ---------------------------------------------------------------------------
# project-groups — базовое покрытие (было 0 тестов)
# ---------------------------------------------------------------------------


def test_project_group_full_crud(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post("/project-groups", headers=headers, json={"name": "Группа X"})
    assert resp.status_code == 200
    group_id = resp.json()["id"]

    resp = client.patch(f"/project-groups/{group_id}", headers=headers, json={"name": "Группа Y"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Группа Y"

    resp = client.delete(f"/project-groups/{group_id}")
    # без заголовков — должно быть отклонено аутентификацией, не 200
    assert resp.status_code in (401, 403)

    resp = client.delete(f"/project-groups/{group_id}", headers=headers)
    assert resp.status_code == 200


def test_project_belongs_to_group_and_group_filter(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    group = make_project_group(db_session, "Стройка")
    project = make_project(db_session, "ЖК Северный", group_id=group.id)

    resp = client.get("/projects", headers=headers)
    row = next(r for r in resp.json() if r["id"] == project.id)
    assert row["group_id"] == group.id


def test_delete_project_group_used_by_project_deactivates(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    group = make_project_group(db_session)
    make_project(db_session, group_id=group.id)

    resp = client.delete(f"/project-groups/{group.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["deactivated"] is True
