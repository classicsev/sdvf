from app.models import RoleEnum, StockMovement
from tests.conftest import auth_headers, make_user


def _setup_variants(client, headers):
    warehouse = client.post("/warehouse/warehouses", headers=headers, json={"name": "Артём"}).json()
    raw_product = client.post("/warehouse/products", headers=headers, json={"name": "Мидия сырая", "unit": "кг"}).json()
    raw_variant = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": raw_product["id"], "name": "стандарт"}
    ).json()
    finished_product = client.post(
        "/warehouse/products", headers=headers, json={"name": "Мидия глазированная", "unit": "кг"}
    ).json()
    finished_variant = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": finished_product["id"], "name": "п/ст"}
    ).json()
    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": raw_variant["id"],
            "direction": "in",
            "quantity": 100,
        },
    )
    return warehouse, raw_variant, finished_variant


def _balances_by_variant(client, headers):
    return {b["product_variant_id"]: b for b in client.get("/warehouse/balances", headers=headers).json()}


def test_create_recipe_and_run_creates_consume_and_yield_movements(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, raw_variant, finished_variant = _setup_variants(client, headers)

    recipe = client.post(
        "/production/recipes",
        headers=headers,
        json={
            "name": "Глазировка мидии",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": 1.5}],
        },
    ).json()
    assert recipe["inputs"][0]["qty_per_unit"] == 1.5

    resp = client.post(
        "/production/runs",
        headers=headers,
        json={"recipe_id": recipe["id"], "warehouse_id": warehouse["id"], "date": "2026-08-05", "output_qty": 10},
    )
    assert resp.status_code == 200, resp.text

    balances = _balances_by_variant(client, headers)
    assert balances[raw_variant["id"]]["quantity"] == 85  # 100 - 1.5*10
    assert balances[finished_variant["id"]]["quantity"] == 10

    movements = client.get(f"/warehouse/movements?warehouse_id={warehouse['id']}", headers=headers).json()
    consume = next(m for m in movements if m["direction"] == "production_consume")
    yield_ = next(m for m in movements if m["direction"] == "production_yield")
    assert consume["quantity"] == 15
    assert consume["production_run_id"] == resp.json()["id"]
    assert yield_["quantity"] == 10
    assert yield_["production_run_id"] == resp.json()["id"]


def test_run_rejects_non_positive_output_qty(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, raw_variant, finished_variant = _setup_variants(client, headers)
    recipe = client.post(
        "/production/recipes",
        headers=headers,
        json={
            "name": "Глазировка",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": 1}],
        },
    ).json()

    resp = client.post(
        "/production/runs",
        headers=headers,
        json={"recipe_id": recipe["id"], "warehouse_id": warehouse["id"], "date": "2026-08-05", "output_qty": 0},
    )
    assert resp.status_code == 400


def test_recipe_requires_at_least_one_input(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, raw_variant, finished_variant = _setup_variants(client, headers)

    resp = client.post(
        "/production/recipes",
        headers=headers,
        json={"name": "Пустая", "output_variant_id": finished_variant["id"], "inputs": []},
    )
    assert resp.status_code == 400


def test_recipe_input_qty_must_be_positive(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, raw_variant, finished_variant = _setup_variants(client, headers)

    resp = client.post(
        "/production/recipes",
        headers=headers,
        json={
            "name": "Некорректная",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": -1}],
        },
    )
    assert resp.status_code == 400


def test_delete_run_removes_stock_movements(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, raw_variant, finished_variant = _setup_variants(client, headers)
    recipe = client.post(
        "/production/recipes",
        headers=headers,
        json={
            "name": "Глазировка",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": 1}],
        },
    ).json()
    run = client.post(
        "/production/runs",
        headers=headers,
        json={"recipe_id": recipe["id"], "warehouse_id": warehouse["id"], "date": "2026-08-05", "output_qty": 5},
    ).json()

    resp = client.delete(f"/production/runs/{run['id']}", headers=headers)
    assert resp.status_code == 200

    remaining = db_session.query(StockMovement).filter(StockMovement.production_run_id == run["id"]).all()
    assert remaining == []

    balances = _balances_by_variant(client, headers)
    assert balances[raw_variant["id"]]["quantity"] == 100
    assert finished_variant["id"] not in balances


def test_update_recipe_replaces_inputs(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, raw_variant, finished_variant = _setup_variants(client, headers)
    recipe = client.post(
        "/production/recipes",
        headers=headers,
        json={
            "name": "Глазировка",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": 1}],
        },
    ).json()

    resp = client.patch(
        f"/production/recipes/{recipe['id']}",
        headers=headers,
        json={
            "name": "Глазировка (новая норма)",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": 2}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Глазировка (новая норма)"
    assert len(resp.json()["inputs"]) == 1
    assert resp.json()["inputs"][0]["qty_per_unit"] == 2


def test_delete_recipe_in_use_deactivates(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, raw_variant, finished_variant = _setup_variants(client, headers)
    recipe = client.post(
        "/production/recipes",
        headers=headers,
        json={
            "name": "Глазировка",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": 1}],
        },
    ).json()
    client.post(
        "/production/runs",
        headers=headers,
        json={"recipe_id": recipe["id"], "warehouse_id": warehouse["id"], "date": "2026-08-05", "output_qty": 5},
    )

    resp = client.delete(f"/production/recipes/{recipe['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": False, "deactivated": True}


def test_delete_unused_recipe_deletes_physically(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, raw_variant, finished_variant = _setup_variants(client, headers)
    recipe = client.post(
        "/production/recipes",
        headers=headers,
        json={
            "name": "Неиспользуемая",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": 1}],
        },
    ).json()

    resp = client.delete(f"/production/recipes/{recipe['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True, "deactivated": False}


def test_viewer_can_read_but_not_write_production(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer)
    warehouse, raw_variant, finished_variant = _setup_variants(client, auth_headers(admin))

    resp = client.get("/production/recipes", headers=auth_headers(viewer))
    assert resp.status_code == 200

    resp = client.post(
        "/production/recipes",
        headers=auth_headers(viewer),
        json={
            "name": "x",
            "output_variant_id": finished_variant["id"],
            "inputs": [{"input_variant_id": raw_variant["id"], "qty_per_unit": 1}],
        },
    )
    assert resp.status_code == 403
