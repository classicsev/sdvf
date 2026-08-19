from app.models import CompanyMember, RoleEnum, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_company, make_project, make_user


def _add_to_company(db_session, user, company, role=RoleEnum.admin):
    db_session.add(CompanyMember(user_id=user.id, company_id=company.id, role=role))
    db_session.commit()


def test_category_by_default_visible_only_in_own_company(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    headers = auth_headers(admin)

    resp = client.post("/categories", headers=headers, json={"name": "Только своя", "type": "expense"})
    assert resp.status_code == 200, resp.text
    category_id = resp.json()["id"]
    own_company_id = resp.json()["company_id"]

    resp = client.get("/categories", headers=headers, params={"company_id": own_company_id})
    assert any(c["id"] == category_id for c in resp.json())

    resp = client.get("/categories", headers=headers, params={"company_id": company_b.id})
    assert not any(c["id"] == category_id for c in resp.json())


def test_category_is_global_visible_in_all_companies_including_future_one(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    headers = auth_headers(admin)

    resp = client.post("/categories", headers=headers, json={"name": "Глобальная", "type": "expense", "is_global": True})
    assert resp.status_code == 200, resp.text
    category_id = resp.json()["id"]

    resp = client.get("/categories", headers=headers, params={"company_id": company_b.id})
    assert any(c["id"] == category_id for c in resp.json())

    # "Динамически" — компания, заведённая ПОСЛЕ создания глобальной статьи,
    # тоже её видит, безо всякой донастройки.
    company_c = make_company(db_session, "Компания В (будущая)")
    _add_to_company(db_session, admin, company_c)
    resp = client.get("/categories", headers=headers, params={"company_id": company_c.id})
    assert any(c["id"] == category_id for c in resp.json())


def test_category_visible_company_ids_shares_with_specific_companies_only(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    company_c = make_company(db_session, "Компания В")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    _add_to_company(db_session, admin, company_c)
    headers = auth_headers(admin)

    resp = client.post(
        "/categories",
        headers=headers,
        json={"name": "Разделяемая", "type": "expense", "visible_company_ids": [company_b.id]},
    )
    assert resp.status_code == 200, resp.text
    category_id = resp.json()["id"]
    assert set(resp.json()["visible_company_ids"]) == {company_b.id}

    resp = client.get("/categories", headers=headers, params={"company_id": company_b.id})
    assert any(c["id"] == category_id for c in resp.json())

    # Компания В в список расшаривания не входила — статья ей не видна.
    resp = client.get("/categories", headers=headers, params={"company_id": company_c.id})
    assert not any(c["id"] == category_id for c in resp.json())


def test_category_visible_company_ids_silently_drops_companies_user_does_not_manage(client, db_session):
    # Пользователь не admin (даже не член) чужой компании — попытка расшарить
    # статью на неё молча игнорируется, а не даёт утечку.
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    other_company = make_company(db_session, "Чужая компания")

    resp = client.post(
        "/categories",
        headers=headers,
        json={"name": "Попытка расшарить", "type": "expense", "visible_company_ids": [other_company.id]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["visible_company_ids"] == []


def test_update_category_replaces_visible_companies_not_accumulates(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    company_c = make_company(db_session, "Компания В")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    _add_to_company(db_session, admin, company_c)
    headers = auth_headers(admin)

    resp = client.post(
        "/categories", headers=headers, json={"name": "X", "type": "expense", "visible_company_ids": [company_b.id]}
    )
    category_id = resp.json()["id"]

    resp = client.patch(
        f"/categories/{category_id}",
        headers=headers,
        json={"name": "X", "type": "expense", "visible_company_ids": [company_c.id]},
    )
    assert resp.status_code == 200, resp.text
    assert set(resp.json()["visible_company_ids"]) == {company_c.id}


def test_category_is_global_switch_clears_stale_visible_company_rows(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    headers = auth_headers(admin)

    resp = client.post(
        "/categories", headers=headers, json={"name": "X", "type": "expense", "visible_company_ids": [company_b.id]}
    )
    category_id = resp.json()["id"]

    resp = client.patch(
        f"/categories/{category_id}",
        headers=headers,
        json={"name": "X", "type": "expense", "is_global": True, "visible_company_ids": [company_b.id]},
    )
    assert resp.status_code == 200, resp.text
    # is_global=true делает поле visible_company_ids избыточным — строки чистятся.
    assert resp.json()["visible_company_ids"] == []


def test_transaction_can_use_globally_visible_category_from_another_company(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    headers = auth_headers(admin)

    resp = client.post("/categories", headers=headers, json={"name": "Глобальная", "type": "income", "is_global": True})
    category_id = resp.json()["id"]

    account = make_account(db_session, company_id=company_b.id)
    resp = client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category_id,
            "type": "income",
            "amount": 100,
            "currency": "RUB",
        },
        params={"company_id": company_b.id},
    )
    assert resp.status_code == 200, resp.text


def test_project_same_visibility_rules_as_category(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    headers = auth_headers(admin)

    resp = client.post("/projects", headers=headers, json={"name": "Глобальный проект", "is_global": True})
    assert resp.status_code == 200, resp.text
    project_id = resp.json()["id"]

    resp = client.get("/projects", headers=headers, params={"company_id": company_b.id})
    assert any(p["id"] == project_id for p in resp.json())


# ---------------------------------------------------------------------------
# Фильтр списка по нескольким компаниям сразу: own_only ("только свои, без
# расшаренных") и match=intersection ("расшарено именно между этими
# компаниями"). См. reference_scope.py::apply_visibility_filter.
# ---------------------------------------------------------------------------


def test_own_only_excludes_items_shared_from_other_company(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    headers = auth_headers(admin)

    resp = client.post(
        "/categories",
        headers=headers,
        json={"name": "Расшаренная из А", "type": "expense", "visible_company_ids": [company_b.id]},
    )
    assert resp.status_code == 200, resp.text
    shared_id = resp.json()["id"]

    resp = client.post(
        "/categories", headers=headers, json={"name": "Своя в Б", "type": "expense"}, params={"company_id": company_b.id}
    )
    assert resp.status_code == 200, resp.text
    own_in_b_id = resp.json()["id"]

    # Без own_only — видны обе (своя в Б + расшаренная из А).
    resp = client.get("/categories", headers=headers, params={"company_id": company_b.id})
    ids = {c["id"] for c in resp.json()}
    assert {shared_id, own_in_b_id} <= ids

    # С own_only=true — только своя в Б, расшаренная из А пропадает.
    resp = client.get("/categories", headers=headers, params={"company_id": company_b.id, "own_only": "true"})
    ids = {c["id"] for c in resp.json()}
    assert own_in_b_id in ids
    assert shared_id not in ids


def test_multi_company_ids_union_by_default(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    headers = auth_headers(admin)

    resp = client.post("/categories", headers=headers, json={"name": "Только А", "type": "expense"})
    only_a_id = resp.json()["id"]
    resp = client.post(
        "/categories", headers=headers, json={"name": "Только Б", "type": "expense"}, params={"company_id": company_b.id}
    )
    only_b_id = resp.json()["id"]

    resp = client.get("/categories", headers=headers, params={"company_ids": [admin.company_id, company_b.id]})
    assert resp.status_code == 200, resp.text
    ids = {c["id"] for c in resp.json()}
    assert only_a_id in ids and only_b_id in ids


def test_multi_company_ids_intersection_shows_only_shared_between_all(client, db_session):
    company_b = make_company(db_session, "Компания Б")
    admin = make_user(db_session, RoleEnum.admin)
    _add_to_company(db_session, admin, company_b)
    headers = auth_headers(admin)

    resp = client.post("/categories", headers=headers, json={"name": "Только А", "type": "expense"})
    only_a_id = resp.json()["id"]
    resp = client.post(
        "/categories",
        headers=headers,
        json={"name": "Расшарена в обе", "type": "expense", "visible_company_ids": [company_b.id]},
    )
    shared_id = resp.json()["id"]

    resp = client.get(
        "/categories",
        headers=headers,
        params={"company_ids": [admin.company_id, company_b.id], "match": "intersection"},
    )
    assert resp.status_code == 200, resp.text
    ids = {c["id"] for c in resp.json()}
    assert shared_id in ids
    assert only_a_id not in ids


def test_multi_company_ids_rejects_inaccessible_company(client, db_session):
    other = make_company(db_session, "Чужая компания")
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.get("/categories", headers=headers, params={"company_ids": [admin.company_id, other.id]})
    assert resp.status_code == 404
