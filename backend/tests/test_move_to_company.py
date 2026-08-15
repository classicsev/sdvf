"""Перенос справочных записей (статьи, проекты, счета, контрагенты) между
компаниями пользователя — задним числом, после создания. См.
utils.py::move_to_company и routers/reference.py::_move_to_company."""

from app.models import Account, Category, Counterparty, CounterpartyContact, Project, RoleEnum, Transaction, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_company, make_counterparty, make_project, make_user


def _second_company_for(client, headers):
    resp = client.post("/companies", json={"name": "Компания Б"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["company"]["id"]


def test_move_unused_category_succeeds(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    category = make_category(db_session, name="Реклама", company_id=admin.company_id)

    resp = client.patch(
        f"/categories/{category.id}/company", headers=headers, json={"company_id": target}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["company_id"] == target

    db_session.refresh(category)
    assert category.company_id == target


def test_move_category_blocked_when_used_by_transaction(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    category = make_category(db_session, tx_type=TxTypeEnum.income, company_id=admin.company_id)
    account = make_account(db_session, company_id=admin.company_id)
    db_session.add(
        Transaction(
            company_id=admin.company_id,
            date_odds="2026-06-01",
            account_id=account.id,
            category_id=category.id,
            type=TxTypeEnum.income,
            amount=100,
            currency="RUB",
            amount_rub=100,
        )
    )
    db_session.commit()

    resp = client.patch(
        f"/categories/{category.id}/company", headers=headers, json={"company_id": target}
    )
    assert resp.status_code == 400
    db_session.refresh(category)
    assert category.company_id == admin.company_id


def test_move_unused_project_succeeds(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    project = make_project(db_session, company_id=admin.company_id)

    resp = client.patch(f"/projects/{project.id}/company", headers=headers, json={"company_id": target})
    assert resp.status_code == 200, resp.text
    assert resp.json()["company_id"] == target


def test_move_unused_account_succeeds(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    account = make_account(db_session, company_id=admin.company_id)

    resp = client.patch(f"/accounts/{account.id}/company", headers=headers, json={"company_id": target})
    assert resp.status_code == 200, resp.text
    assert resp.json()["company_id"] == target


def test_move_account_blocked_when_used_by_transaction(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    account = make_account(db_session, company_id=admin.company_id)
    category = make_category(db_session, tx_type=TxTypeEnum.income, company_id=admin.company_id)
    db_session.add(
        Transaction(
            company_id=admin.company_id,
            date_odds="2026-06-01",
            account_id=account.id,
            category_id=category.id,
            type=TxTypeEnum.income,
            amount=100,
            currency="RUB",
            amount_rub=100,
        )
    )
    db_session.commit()

    resp = client.patch(f"/accounts/{account.id}/company", headers=headers, json={"company_id": target})
    assert resp.status_code == 400


def test_move_unused_counterparty_succeeds(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    counterparty = make_counterparty(db_session, company_id=admin.company_id)

    resp = client.patch(
        f"/counterparties/{counterparty.id}/company", headers=headers, json={"company_id": target}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["company_id"] == target


def test_move_counterparty_blocked_when_it_has_contacts(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    target = _second_company_for(client, headers)
    counterparty = make_counterparty(db_session, company_id=admin.company_id)
    db_session.add(
        CounterpartyContact(
            company_id=admin.company_id, counterparty_id=counterparty.id, full_name="Иванов Иван"
        )
    )
    db_session.commit()

    resp = client.patch(
        f"/counterparties/{counterparty.id}/company", headers=headers, json={"company_id": target}
    )
    assert resp.status_code == 400


def test_move_requires_admin_in_target_company_too(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    category = make_category(db_session, company_id=admin.company_id)

    # Компания существует, но admin в ней вообще не состоит — не 403 (это
    # означало бы подтверждение существования чужой компании), а 404, тот же
    # принцип, что и у check_company_role везде в кодовой базе.
    other_company = make_company(db_session, name="Чужая компания")

    resp = client.patch(
        f"/categories/{category.id}/company", headers=headers, json={"company_id": other_company.id}
    )
    assert resp.status_code == 404
    db_session.refresh(category)
    assert category.company_id == admin.company_id


def test_move_forbidden_when_only_non_admin_in_target(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    category = make_category(db_session, company_id=admin.company_id)

    target = make_company(db_session, name="Компания Б")
    from app.models import CompanyMember

    db_session.add(CompanyMember(user_id=admin.id, company_id=target.id, role=RoleEnum.viewer))
    db_session.commit()

    resp = client.patch(
        f"/categories/{category.id}/company", headers=headers, json={"company_id": target.id}
    )
    assert resp.status_code == 403
    db_session.refresh(category)
    assert category.company_id == admin.company_id


def test_move_requires_admin_in_source_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer, company_id=admin.company_id)
    target = make_company(db_session, name="Компания Б")
    # viewer тоже admin в целевой компании — но не в исходной
    from app.models import CompanyMember

    db_session.add(CompanyMember(user_id=viewer.id, company_id=target.id, role=RoleEnum.admin))
    db_session.commit()
    category = make_category(db_session, company_id=admin.company_id)

    resp = client.patch(
        f"/categories/{category.id}/company", headers=auth_headers(viewer), json={"company_id": target.id}
    )
    assert resp.status_code == 403


def test_move_category_not_found_for_inaccessible_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other_company = make_company(db_session, name="Чужая компания")
    other_category = make_category(db_session, company_id=other_company.id)

    resp = client.patch(
        f"/categories/{other_category.id}/company",
        headers=auth_headers(admin),
        json={"company_id": other_company.id},
    )
    assert resp.status_code == 404
