"""Массовое распределение статей/проектов по компаниям — POST .../bulk-visibility.
В отличие от формы редактирования одной записи (которая заменяет видимость
целиком), тут ДОБАВЛЯЕМ компании сразу нескольким выбранным записям, и бэкенд
сам сливает дубли с тем же названием, если они уже есть в целевой компании.
См. routers/reference.py::_bulk_distribute."""

from app.models import Category, CategoryCompany, Transaction, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_project, make_user
from app.models import RoleEnum


def _second_company_for(client, headers):
    resp = client.post("/companies", json={"name": "Компания Б"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["company"]["id"]


def test_bulk_visibility_adds_target_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    category = make_category(db_session, name="Реклама", company_id=admin.company_id)

    resp = client.post(
        "/categories/bulk-visibility", headers=headers, json={"ids": [category.id], "company_ids": [target]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == 1
    assert body["merged_names"] == []

    db_session.refresh(category)
    assert target in category.visible_company_ids


def test_bulk_visibility_merges_duplicate_in_target_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    category = make_category(db_session, name="Реклама", tx_type=TxTypeEnum.expense, company_id=admin.company_id)
    duplicate = make_category(db_session, name="реклама", tx_type=TxTypeEnum.expense, company_id=target)
    duplicate_id = duplicate.id
    account = make_account(db_session, company_id=target)
    db_session.add(
        Transaction(
            company_id=target,
            date_odds="2026-06-01",
            account_id=account.id,
            category_id=duplicate_id,
            type=TxTypeEnum.expense,
            amount=100,
            currency="RUB",
            amount_rub=100,
        )
    )
    db_session.commit()

    resp = client.post(
        "/categories/bulk-visibility", headers=headers, json={"ids": [category.id], "company_ids": [target]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["merged_names"] == ["реклама"]

    assert db_session.query(Category).filter(Category.id == duplicate_id).first() is None
    tx = db_session.query(Transaction).filter(Transaction.company_id == target).one()
    assert tx.category_id == category.id
    db_session.refresh(category)
    assert target in category.visible_company_ids


def test_bulk_visibility_is_global_clears_company_links(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    _second_company_for(client, headers)
    category = make_category(db_session, name="Аренда", company_id=admin.company_id)

    resp = client.post(
        "/categories/bulk-visibility", headers=headers, json={"ids": [category.id], "is_global": True}
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(category)
    assert category.is_global is True
    assert db_session.query(CategoryCompany).filter(CategoryCompany.category_id == category.id).count() == 0


def test_bulk_visibility_skips_records_user_does_not_admin(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer, company_id=admin.company_id)
    headers = auth_headers(viewer)
    category = make_category(db_session, name="Связь", company_id=admin.company_id)

    resp = client.post("/categories/bulk-visibility", headers=headers, json={"ids": [category.id], "company_ids": []})
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 0


def test_bulk_visibility_projects(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    project = make_project(db_session, name="Стройка", company_id=admin.company_id)

    resp = client.post(
        "/projects/bulk-visibility", headers=headers, json={"ids": [project.id], "company_ids": [target]}
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(project)
    assert target in project.visible_company_ids
