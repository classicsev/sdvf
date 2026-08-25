from app.models import RoleEnum
from tests.conftest import auth_headers, make_user


def test_admin_can_create_and_list_fixed_asset(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post(
        "/fixed-assets",
        headers=headers,
        json={"name": "Холодильник", "purchase_date": "2026-01-01", "purchase_cost_rub": 100000, "useful_life_months": 24},
    )
    assert resp.status_code == 200, resp.text

    resp = client.get("/fixed-assets", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["book_value_rub"] is not None


def test_operator_cannot_create_fixed_asset(client, db_session):
    operator = make_user(db_session, RoleEnum.operator)
    headers = auth_headers(operator)

    resp = client.post(
        "/fixed-assets",
        headers=headers,
        json={"name": "Холодильник", "purchase_date": "2026-01-01", "purchase_cost_rub": 100000, "useful_life_months": 24},
    )
    assert resp.status_code == 403


def test_delete_fixed_asset(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    asset = client.post(
        "/fixed-assets",
        headers=headers,
        json={"name": "Станок", "purchase_date": "2026-01-01", "purchase_cost_rub": 50000, "useful_life_months": 12},
    ).json()

    resp = client.delete(f"/fixed-assets/{asset['id']}", headers=headers)
    assert resp.status_code == 200
    assert client.get("/fixed-assets", headers=headers).json() == []


def test_book_value_floors_at_zero_after_useful_life(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    client.post(
        "/fixed-assets",
        headers=headers,
        json={"name": "Старое ОС", "purchase_date": "2020-01-01", "purchase_cost_rub": 10000, "useful_life_months": 12},
    )
    resp = client.get("/fixed-assets", headers=headers, params={"as_of": "2026-08-25"})
    assert resp.json()[0]["book_value_rub"] == 0.0
