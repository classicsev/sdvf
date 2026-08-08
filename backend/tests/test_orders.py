from app.models import RoleEnum, StockMovement
from tests.conftest import auth_headers, make_counterparty, make_user


def _setup_catalog(client, headers):
    warehouse = client.post("/warehouse/warehouses", headers=headers, json={"name": "Артём"}).json()
    product = client.post("/warehouse/products", headers=headers, json={"name": "Устрица Императорская", "unit": "кг"}).json()
    variant = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": "40/60"}
    ).json()
    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 100,
        },
    )
    return warehouse, product, variant


def test_create_order_with_lines(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session, name="Эверест Астрахань")

    resp = client.post(
        "/orders",
        headers=headers,
        json={
            "counterparty_id": cp.id,
            "warehouse_id": warehouse["id"],
            "lines": [{"product_variant_id": variant["id"], "quantity": 10}],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert len(body["lines"]) == 1
    assert body["lines"][0]["quantity"] == 10


def test_order_requires_at_least_one_line(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    resp = client.post(
        "/orders", headers=headers, json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": []}
    )
    assert resp.status_code == 400


def test_reserve_reduces_available_and_ship_creates_stock_movement(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order = client.post(
        "/orders",
        headers=headers,
        json={
            "counterparty_id": cp.id,
            "warehouse_id": warehouse["id"],
            "lines": [{"product_variant_id": variant["id"], "quantity": 30}],
        },
    ).json()

    resp = client.post(f"/orders/{order['id']}/reserve", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "reserved"

    balances = {b["product_variant_id"]: b for b in client.get("/warehouse/balances", headers=headers).json()}
    row = balances[variant["id"]]
    assert row["quantity"] == 100
    assert row["reserved"] == 30
    assert row["available"] == 70

    resp = client.post(f"/orders/{order['id']}/ship", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "shipped"

    movements = client.get(f"/warehouse/movements?warehouse_id={warehouse['id']}", headers=headers).json()
    ship_movement = next(m for m in movements if m["direction"] == "out")
    assert ship_movement["quantity"] == 30
    assert ship_movement["order_id"] == order["id"]

    balances_after = {b["product_variant_id"]: b for b in client.get("/warehouse/balances", headers=headers).json()}
    row_after = balances_after[variant["id"]]
    assert row_after["quantity"] == 70
    # заказ уже отгружен (не reserved) -> больше не резервирует
    assert row_after["reserved"] == 0
    assert row_after["available"] == 70


def test_ship_directly_from_draft_without_reserve(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order = client.post(
        "/orders",
        headers=headers,
        json={
            "counterparty_id": cp.id,
            "warehouse_id": warehouse["id"],
            "lines": [{"product_variant_id": variant["id"], "quantity": 5}],
        },
    ).json()

    resp = client.post(f"/orders/{order['id']}/ship", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "shipped"


def test_cancel_from_draft_and_reserved(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order1 = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()
    resp = client.post(f"/orders/{order1['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    order2 = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()
    client.post(f"/orders/{order2['id']}/reserve", headers=headers)
    resp = client.post(f"/orders/{order2['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # отменённый заказ больше не резервирует остаток
    balances = {b["product_variant_id"]: b for b in client.get("/warehouse/balances", headers=headers).json()}
    assert balances[variant["id"]]["reserved"] == 0


def test_invalid_transitions_rejected(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()
    client.post(f"/orders/{order['id']}/cancel", headers=headers)

    assert client.post(f"/orders/{order['id']}/reserve", headers=headers).status_code == 400
    assert client.post(f"/orders/{order['id']}/ship", headers=headers).status_code == 400
    assert client.post(f"/orders/{order['id']}/cancel", headers=headers).status_code == 400


def test_add_and_remove_line_only_in_draft(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)
    variant2 = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": "60/100"}
    ).json()

    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()

    resp = client.post(
        f"/orders/{order['id']}/lines", headers=headers, json={"product_variant_id": variant2["id"], "quantity": 3}
    )
    assert resp.status_code == 200
    assert len(resp.json()["lines"]) == 2

    line_id = resp.json()["lines"][0]["id"]
    resp = client.delete(f"/orders/{order['id']}/lines/{line_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["lines"]) == 1

    client.post(f"/orders/{order['id']}/reserve", headers=headers)
    resp = client.post(
        f"/orders/{order['id']}/lines", headers=headers, json={"product_variant_id": variant["id"], "quantity": 1}
    )
    assert resp.status_code == 400


def test_delete_order_only_in_draft(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()
    client.post(f"/orders/{order['id']}/reserve", headers=headers)
    resp = client.delete(f"/orders/{order['id']}", headers=headers)
    assert resp.status_code == 400

    order2 = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()
    resp = client.delete(f"/orders/{order2['id']}", headers=headers)
    assert resp.status_code == 200


def test_list_orders_filters(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()

    resp = client.get(f"/orders?status_filter=draft&warehouse_id={warehouse['id']}&counterparty_id={cp.id}", headers=headers)
    assert resp.status_code == 200
    assert any(o["id"] == order["id"] for o in resp.json())

    resp = client.get("/orders?status_filter=shipped", headers=headers)
    assert not any(o["id"] == order["id"] for o in resp.json())


def test_update_order_note_and_blocked_when_closed(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()

    resp = client.patch(f"/orders/{order['id']}", headers=headers, json={"note": "срочно"})
    assert resp.status_code == 200
    assert resp.json()["note"] == "срочно"

    client.post(f"/orders/{order['id']}/ship", headers=headers)
    resp = client.patch(f"/orders/{order['id']}", headers=headers, json={"note": "поздно"})
    assert resp.status_code == 400


def test_create_order_rejects_non_positive_line_quantity(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    resp = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 0}]},
    )
    assert resp.status_code == 400


def test_add_line_rejects_non_positive_quantity(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()
    resp = client.post(f"/orders/{order['id']}/lines", headers=headers, json={"product_variant_id": variant["id"], "quantity": -1})
    assert resp.status_code == 400


def test_remove_line_from_wrong_order_404(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)

    order1 = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()
    order2 = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()

    line_id_of_order1 = order1["lines"][0]["id"]
    resp = client.delete(f"/orders/{order2['id']}/lines/{line_id_of_order1}", headers=headers)
    assert resp.status_code == 404


def test_viewer_can_read_but_not_write_orders(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer)
    warehouse, product, variant = _setup_catalog(client, auth_headers(admin))
    cp = make_counterparty(db_session)

    resp = client.get("/orders", headers=auth_headers(viewer))
    assert resp.status_code == 200

    resp = client.post(
        "/orders",
        headers=auth_headers(viewer),
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    )
    assert resp.status_code == 403
