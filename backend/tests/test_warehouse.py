from app.models import PayrollAccrual, PayrollPayment, RoleEnum, StockMovement
from tests.conftest import auth_headers, make_account, make_user


def _setup_catalog(client, headers, product_name="Устрица Императорская"):
    warehouse = client.post("/warehouse/warehouses", headers=headers, json={"name": "Артём"}).json()
    product = client.post("/warehouse/products", headers=headers, json={"name": product_name, "unit": "кг"}).json()
    variant = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": "40/60"}
    ).json()
    return warehouse, product, variant


def test_movement_in_and_out_update_balance(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    resp = client.post(
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
    assert resp.status_code == 200, resp.text

    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-03",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "out",
            "quantity": 30,
        },
    )

    balances = client.get("/warehouse/balances", headers=headers).json()
    row = next(b for b in balances if b["product_variant_id"] == variant["id"])
    assert row["quantity"] == 70
    assert row["warehouse_name"] == "Артём"
    assert row["product_name"] == "Устрица Императорская"


def test_balances_are_sorted_by_warehouse_product_and_numeric_calibration(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse = client.post("/warehouse/warehouses", headers=headers, json={"name": "Артём"}).json()
    product = client.post("/warehouse/products", headers=headers, json={"name": "Устрица", "unit": "кг"}).json()

    # Специально создаём калибры не по порядку, чтобы проверить, что сортировка
    # в ответе — числовая по калибру, а не по алфавиту строки ("100/150" < "40/60").
    variants = {}
    for cal in ["100/150", "40/60", "300/500", "60/100"]:
        variants[cal] = client.post(
            "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": cal}
        ).json()

    for cal, v in variants.items():
        client.post(
            "/warehouse/movements",
            headers=headers,
            json={
                "date": "2026-08-02",
                "warehouse_id": warehouse["id"],
                "product_variant_id": v["id"],
                "direction": "in",
                "quantity": 10,
            },
        )

    balances = client.get("/warehouse/balances", headers=headers).json()
    calibrations_in_order = [b["variant_name"] for b in balances]
    assert calibrations_in_order == ["40/60", "60/100", "100/150", "300/500"]


def test_balances_include_empty_shows_variants_without_movements(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    # Второй калибр создан, но по нему ни разу не было движения.
    empty_variant = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": "60/100"}
    ).json()

    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 10,
        },
    )

    default_resp = client.get("/warehouse/balances", headers=headers).json()
    assert empty_variant["id"] not in [b["product_variant_id"] for b in default_resp]

    full_resp = client.get("/warehouse/balances?include_empty=true", headers=headers).json()
    by_variant = {b["product_variant_id"]: b for b in full_resp}
    assert variant["id"] in by_variant
    assert empty_variant["id"] in by_variant
    assert by_variant[empty_variant["id"]]["quantity"] == 0
    assert by_variant[empty_variant["id"]]["available"] == 0


def test_adjustment_can_be_negative(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 50,
        },
    )
    resp = client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-04",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "adjustment",
            "quantity": -5,
            "note": "инвентаризация: недостача",
        },
    )
    assert resp.status_code == 200, resp.text

    balances = client.get("/warehouse/balances", headers=headers).json()
    row = next(b for b in balances if b["product_variant_id"] == variant["id"])
    assert row["quantity"] == 45


def test_direct_create_rejects_transfer_and_production_directions(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    resp = client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "transfer_in",
            "quantity": 10,
        },
    )
    assert resp.status_code == 400


def test_transfer_creates_paired_movements(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse_a, product, variant = _setup_catalog(client, headers)
    warehouse_b = client.post("/warehouse/warehouses", headers=headers, json={"name": "Москва"}).json()

    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse_a["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 100,
        },
    )

    resp = client.post(
        "/warehouse/movements/transfer",
        headers=headers,
        json={
            "date": "2026-08-05",
            "product_variant_id": variant["id"],
            "from_warehouse_id": warehouse_a["id"],
            "to_warehouse_id": warehouse_b["id"],
            "quantity": 40,
        },
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2

    balances = {b["warehouse_id"]: b["quantity"] for b in client.get("/warehouse/balances", headers=headers).json()}
    assert balances[warehouse_a["id"]] == 60
    assert balances[warehouse_b["id"]] == 40


def test_payroll_bridge_creates_accrual_on_in_movement(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    employee = client.post("/payroll/employees", headers=headers, json={"full_name": "Юра Добрый"}).json()

    resp = client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 20,
            "executor_id": employee["id"],
            "payroll_rate": 40,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["payroll_accrual_id"] is not None

    accrual = db_session.get(PayrollAccrual, body["payroll_accrual_id"])
    assert accrual.employee_id == employee["id"]
    assert float(accrual.total) == 800.0
    assert accrual.period.isoformat() == "2026-08-01"


def test_movement_without_executor_does_not_create_accrual(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    resp = client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 20,
        },
    )
    assert resp.json()["payroll_accrual_id"] is None


def test_delete_movement_removes_linked_accrual(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    employee = client.post("/payroll/employees", headers=headers, json={"full_name": "Илья"}).json()

    movement = client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 10,
            "executor_id": employee["id"],
            "payroll_rate": 40,
        },
    ).json()
    accrual_id = movement["payroll_accrual_id"]

    resp = client.delete(f"/warehouse/movements/{movement['id']}", headers=headers)
    assert resp.status_code == 200
    assert db_session.get(StockMovement, movement["id"]) is None
    assert db_session.get(PayrollAccrual, accrual_id) is None


def test_delete_movement_blocked_if_accrual_already_paid(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    employee = client.post("/payroll/employees", headers=headers, json={"full_name": "Антон"}).json()
    account = make_account(db_session)

    movement = client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 10,
            "executor_id": employee["id"],
            "payroll_rate": 40,
        },
    ).json()

    client.post(
        "/payroll/payments",
        headers=headers,
        json={
            "employee_id": employee["id"],
            "accrual_id": movement["payroll_accrual_id"],
            "account_id": account.id,
            "date": "2026-08-10",
            "amount": 400,
            "payment_type": "ЗП",
        },
    )

    resp = client.delete(f"/warehouse/movements/{movement['id']}", headers=headers)
    assert resp.status_code == 400
    assert db_session.get(StockMovement, movement["id"]) is not None


def test_delete_warehouse_in_use_deactivates_instead_of_erroring(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 10,
        },
    )

    resp = client.delete(f"/warehouse/warehouses/{warehouse['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": False, "deactivated": True}


def test_viewer_can_read_but_not_write(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer)
    warehouse, product, variant = _setup_catalog(client, auth_headers(admin))

    resp = client.get("/warehouse/balances", headers=auth_headers(viewer))
    assert resp.status_code == 200

    resp = client.post("/warehouse/warehouses", headers=auth_headers(viewer), json={"name": "x"})
    assert resp.status_code == 403


def test_update_warehouse_product_variant(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    resp = client.patch(f"/warehouse/warehouses/{warehouse['id']}", headers=headers, json={"name": "Артём (переименован)"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Артём (переименован)"

    resp = client.patch(f"/warehouse/products/{product['id']}", headers=headers, json={"name": "Устрица Хасанская", "unit": "кг"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Устрица Хасанская"

    resp = client.patch(
        f"/warehouse/variants/{variant['id']}", headers=headers, json={"product_id": product["id"], "name": "60/100"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "60/100"


def test_filters_on_lists_and_balances(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    other_product = client.post("/warehouse/products", headers=headers, json={"name": "Мидия"}).json()

    resp = client.get(f"/warehouse/variants?product_id={product['id']}", headers=headers)
    assert resp.status_code == 200
    assert all(v["product_id"] == product["id"] for v in resp.json())

    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 15,
        },
    )
    resp = client.get(f"/warehouse/movements?warehouse_id={warehouse['id']}&product_variant_id={variant['id']}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get(f"/warehouse/balances?warehouse_id={warehouse['id']}", headers=headers)
    assert all(b["warehouse_id"] == warehouse["id"] for b in resp.json())
    assert other_product["id"]  # использован только чтобы не мешать остальным остаткам


def test_movement_rejects_non_positive_quantity_for_in_out(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    resp = client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 0,
        },
    )
    assert resp.status_code == 400


def test_movement_rejects_unknown_executor(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    resp = client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant["id"],
            "direction": "in",
            "quantity": 5,
            "executor_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert resp.status_code == 404


def test_transfer_rejects_same_warehouse_and_non_positive_quantity(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    resp = client.post(
        "/warehouse/movements/transfer",
        headers=headers,
        json={
            "date": "2026-08-02",
            "product_variant_id": variant["id"],
            "from_warehouse_id": warehouse["id"],
            "to_warehouse_id": warehouse["id"],
            "quantity": 5,
        },
    )
    assert resp.status_code == 400

    other_warehouse = client.post("/warehouse/warehouses", headers=headers, json={"name": "Москва"}).json()
    resp = client.post(
        "/warehouse/movements/transfer",
        headers=headers,
        json={
            "date": "2026-08-02",
            "product_variant_id": variant["id"],
            "from_warehouse_id": warehouse["id"],
            "to_warehouse_id": other_warehouse["id"],
            "quantity": 0,
        },
    )
    assert resp.status_code == 400


def test_delete_product_and_variant_in_use_deactivate(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)

    resp = client.delete(f"/warehouse/variants/{variant['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True, "deactivated": False}

    variant2 = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": "60/100"}
    ).json()
    client.post(
        "/warehouse/movements",
        headers=headers,
        json={
            "date": "2026-08-02",
            "warehouse_id": warehouse["id"],
            "product_variant_id": variant2["id"],
            "direction": "in",
            "quantity": 5,
        },
    )
    resp = client.delete(f"/warehouse/variants/{variant2['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": False, "deactivated": True}

    resp = client.delete(f"/warehouse/products/{product['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": False, "deactivated": True}


def test_warehouse_employees_endpoint_hides_bank_details_and_is_open_to_warehouse_operator(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    wh_op = make_user(db_session, RoleEnum.warehouse_operator)

    client.post(
        "/payroll/employees",
        headers=auth_headers(admin),
        json={"full_name": "Юра Добрый", "bank_details": "40817810000000000001"},
    )

    resp = client.get("/warehouse/employees", headers=auth_headers(wh_op))
    assert resp.status_code == 200
    assert resp.json() == [{"id": resp.json()[0]["id"], "full_name": "Юра Добрый"}]
    assert "bank_details" not in resp.json()[0]


def test_warehouse_operator_can_write_but_not_touch_payroll_employees_alone(client, db_session):
    wh_op = make_user(db_session, RoleEnum.warehouse_operator)
    headers = auth_headers(wh_op)

    resp = client.post("/warehouse/warehouses", headers=headers, json={"name": "Русский остров"})
    assert resp.status_code == 200, resp.text

    # Складской оператор не должен иметь доступа к финансовому контуру на запись
    resp = client.post(
        "/transactions",
        headers=headers,
        json={"date_odds": "2026-08-02", "account_id": "x", "category_id": "x", "type": "expense", "amount": 1, "currency": "RUB"},
    )
    assert resp.status_code == 403
