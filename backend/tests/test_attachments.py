from app.models import RoleEnum
from tests.conftest import auth_headers, make_company, make_counterparty, make_user


def _make_order(client, headers):
    warehouse = client.post("/warehouse/warehouses", headers=headers, json={"name": "Артём"}).json()
    product = client.post("/warehouse/products", headers=headers, json={"name": "Устрица", "unit": "кг"}).json()
    variant = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": "40/60"}
    ).json()
    return warehouse, variant


def test_upload_list_delete_attachment_on_order(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, variant = _make_order(client, headers)
    cp = make_counterparty(db_session)
    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()

    resp = client.post(
        "/attachments",
        headers=headers,
        params={"entity_type": "order", "entity_id": order["id"]},
        files={"file": ("contract.pdf", b"%PDF-1.4 fake contents", "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    attachment = resp.json()
    assert attachment["filename"] == "contract.pdf"
    assert attachment["url"].startswith("/media/attachments/")

    resp = client.get("/attachments", headers=headers, params={"entity_type": "order", "entity_id": order["id"]})
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.delete(f"/attachments/{attachment['id']}", headers=headers)
    assert resp.status_code == 200
    resp = client.get("/attachments", headers=headers, params={"entity_type": "order", "entity_id": order["id"]})
    assert resp.json() == []


def test_upload_rejects_disallowed_content_type(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, variant = _make_order(client, headers)
    cp = make_counterparty(db_session)
    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()

    resp = client.post(
        "/attachments",
        headers=headers,
        params={"entity_type": "order", "entity_id": order["id"]},
        files={"file": ("virus.exe", b"MZ fake exe", "application/x-msdownload")},
    )
    assert resp.status_code == 400


def test_attachment_isolated_by_company(client, db_session):
    """Пользователь другой компании не должен видеть вложения к чужому заказу —
    та же изоляция, что и у самих сущностей (get_or_404_accessible)."""
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, variant = _make_order(client, headers)
    cp = make_counterparty(db_session)
    order = client.post(
        "/orders",
        headers=headers,
        json={"counterparty_id": cp.id, "warehouse_id": warehouse["id"], "lines": [{"product_variant_id": variant["id"], "quantity": 5}]},
    ).json()
    client.post(
        "/attachments",
        headers=headers,
        params={"entity_type": "order", "entity_id": order["id"]},
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )

    other_company = make_company(db_session, name="Другая компания")
    other_admin = make_user(db_session, RoleEnum.admin, company_id=other_company.id)
    resp = client.get(
        "/attachments", headers=auth_headers(other_admin), params={"entity_type": "order", "entity_id": order["id"]}
    )
    assert resp.status_code == 404
