from app.models import RoleEnum
from tests.conftest import auth_headers, make_user


def _setup(client, headers):
    warehouse = client.post("/warehouse/warehouses", headers=headers, json={"name": "Артём"}).json()
    product = client.post("/warehouse/products", headers=headers, json={"name": "Устрица", "unit": "кг"}).json()
    variant = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": "40/60"}
    ).json()
    return warehouse, variant


def _movement(client, headers, warehouse, variant, direction, quantity, unit_cost_rub=None):
    payload = {
        "date": "2026-08-25",
        "warehouse_id": warehouse["id"],
        "product_variant_id": variant["id"],
        "direction": direction,
        "quantity": quantity,
    }
    if unit_cost_rub is not None:
        payload["unit_cost_rub"] = unit_cost_rub
    resp = client.post("/warehouse/movements", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_first_prihod_with_cost_sets_avg_cost(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, variant = _setup(client, headers)

    _movement(client, headers, warehouse, variant, "in", 100, unit_cost_rub=50)

    variants = client.get(f"/warehouse/variants?product_id={variant['product_id']}", headers=headers).json()
    updated = next(v for v in variants if v["id"] == variant["id"])
    assert updated["avg_cost_rub"] == 50.0


def test_second_prihod_recomputes_weighted_average(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, variant = _setup(client, headers)

    _movement(client, headers, warehouse, variant, "in", 100, unit_cost_rub=50)  # 100 * 50 = 5000
    _movement(client, headers, warehouse, variant, "in", 100, unit_cost_rub=70)  # +100 * 70 = 7000

    # (5000 + 7000) / 200 = 60
    variants = client.get(f"/warehouse/variants?product_id={variant['product_id']}", headers=headers).json()
    updated = next(v for v in variants if v["id"] == variant["id"])
    assert updated["avg_cost_rub"] == 60.0


def test_rashod_does_not_change_avg_cost(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, variant = _setup(client, headers)

    _movement(client, headers, warehouse, variant, "in", 100, unit_cost_rub=50)
    _movement(client, headers, warehouse, variant, "out", 30)  # без цены — расход её не меняет

    variants = client.get(f"/warehouse/variants?product_id={variant['product_id']}", headers=headers).json()
    updated = next(v for v in variants if v["id"] == variant["id"])
    assert updated["avg_cost_rub"] == 50.0


def test_prihod_without_cost_does_not_touch_existing_avg_cost(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, variant = _setup(client, headers)

    _movement(client, headers, warehouse, variant, "in", 100, unit_cost_rub=50)
    _movement(client, headers, warehouse, variant, "in", 50)  # без цены — не пересчитывает

    variants = client.get(f"/warehouse/variants?product_id={variant['product_id']}", headers=headers).json()
    updated = next(v for v in variants if v["id"] == variant["id"])
    assert updated["avg_cost_rub"] == 50.0
