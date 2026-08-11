from app.models import RoleEnum, Transaction, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_company, make_user


def _make_second_company(client, admin_headers):
    resp = client.post("/companies", json={"name": "Компания Б"}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["company"]["id"]


def _seed_transaction(db_session, company_id, amount=500):
    account = make_account(db_session, company_id=company_id)
    category = make_category(db_session, tx_type=TxTypeEnum.income, company_id=company_id)
    tx = Transaction(
        company_id=company_id,
        date_odds="2026-06-01",
        account_id=account.id,
        category_id=category.id,
        type=TxTypeEnum.income,
        amount=amount,
        currency="RUB",
        amount_rub=amount,
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    return tx


def test_list_transactions_combines_all_companies_by_default(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    _seed_transaction(db_session, admin.company_id, amount=100)
    _seed_transaction(db_session, company_b, amount=200)

    resp = client.get("/transactions", headers=headers)
    assert resp.status_code == 200
    amounts = sorted(tx["amount"] for tx in resp.json())
    assert amounts == [100.0, 200.0]


def test_list_transactions_filtered_to_one_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)

    _seed_transaction(db_session, admin.company_id, amount=100)
    _seed_transaction(db_session, company_b, amount=200)

    resp = client.get("/transactions", params={"company_id": company_b}, headers=headers)
    assert resp.status_code == 200
    amounts = [tx["amount"] for tx in resp.json()]
    assert amounts == [200.0]


def test_list_transactions_rejects_company_id_without_access(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other_company = make_company(db_session, name="Чужая компания")
    other_admin = make_user(db_session, RoleEnum.admin, company_id=other_company.id)

    resp = client.get(
        "/transactions", params={"company_id": other_admin.company_id}, headers=auth_headers(admin)
    )
    assert resp.status_code == 404


def test_admin_can_edit_transaction_in_second_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)
    tx = _seed_transaction(db_session, company_b, amount=100)

    resp = client.patch(f"/transactions/{tx.id}", json={"comment": "правка"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["comment"] == "правка"


def test_viewer_in_second_company_cannot_edit(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b_id = _make_second_company(client, headers)
    tx = _seed_transaction(db_session, company_b_id, amount=100)

    viewer = make_user(db_session, RoleEnum.viewer, company_id=company_b_id)
    resp = client.patch(f"/transactions/{tx.id}", json={"comment": "х"}, headers=auth_headers(viewer))
    assert resp.status_code == 403


def test_cannot_access_transaction_in_company_without_membership(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other_company = make_company(db_session, name="Чужая компания 2")
    tx = _seed_transaction(db_session, other_company.id, amount=100)

    resp = client.patch(f"/transactions/{tx.id}", json={"comment": "х"}, headers=auth_headers(admin))
    assert resp.status_code == 404


def test_create_transaction_targets_selected_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)
    account = make_account(db_session, company_id=company_b)
    category = make_category(db_session, tx_type=TxTypeEnum.income, company_id=company_b)

    resp = client.post(
        "/transactions",
        params={"company_id": company_b},
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 300,
            "currency": "RUB",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["company_id"] == company_b


def test_create_transaction_rejects_account_from_other_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)
    # Счёт и статья принадлежат основной компании admin, а не company_b.
    account = make_account(db_session, company_id=admin.company_id)
    category = make_category(db_session, tx_type=TxTypeEnum.income, company_id=admin.company_id)

    resp = client.post(
        "/transactions",
        params={"company_id": company_b},
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": category.id,
            "type": "income",
            "amount": 300,
            "currency": "RUB",
        },
        headers=headers,
    )
    assert resp.status_code == 404


def test_update_transaction_rejects_account_from_other_company(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    company_b = _make_second_company(client, headers)
    tx = _seed_transaction(db_session, company_b, amount=100)
    # Счёт из основной компании admin — не должен быть принят для операции company_b.
    foreign_account = make_account(db_session, company_id=admin.company_id)

    resp = client.patch(
        f"/transactions/{tx.id}", json={"account_id": foreign_account.id}, headers=headers
    )
    assert resp.status_code == 404
