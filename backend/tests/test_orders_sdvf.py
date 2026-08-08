import httpx

from app.config import settings
from app.integrations.sdvf import SdvfClient, SdvfError
from app.models import RoleEnum
from tests.conftest import auth_headers, make_counterparty, make_user


def _setup_catalog(client, headers):
    warehouse = client.post("/warehouse/warehouses", headers=headers, json={"name": "Артём"}).json()
    product = client.post(
        "/warehouse/products", headers=headers, json={"name": "Устрица Императорская", "unit": "кг"}
    ).json()
    variant = client.post(
        "/warehouse/variants", headers=headers, json={"product_id": product["id"], "name": "40/60"}
    ).json()
    return warehouse, product, variant


def _make_order(client, headers, warehouse, variant, counterparty, quantity=10):
    resp = client.post(
        "/orders",
        headers=headers,
        json={
            "counterparty_id": counterparty.id,
            "warehouse_id": warehouse["id"],
            "lines": [{"product_variant_id": variant["id"], "quantity": quantity}],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _configure_sdvf(monkeypatch):
    monkeypatch.setattr(settings, "sdvf_base_url", "https://sdvf.ru")
    monkeypatch.setattr(settings, "sdvf_api_key", "test-key")


def test_generate_invoice_503_when_not_configured(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)
    order = _make_order(client, headers, warehouse, variant, cp)

    resp = client.post(f"/orders/{order['id']}/generate-invoice", headers=headers, json={"lines": []})
    assert resp.status_code == 503


def test_generate_invoice_requires_company_org_details(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)
    cp.inn = "7801234567"
    db_session.commit()
    order = _make_order(client, headers, warehouse, variant, cp)

    resp = client.post(
        f"/orders/{order['id']}/generate-invoice",
        headers=headers,
        json={"lines": [{"order_line_id": order["lines"][0]["id"], "price": 350}]},
    )
    assert resp.status_code == 400
    assert "реквизиты" in resp.json()["detail"].lower()


def test_generate_invoice_requires_counterparty_inn(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    admin.company.sdvf_org_naming = "ООО Щёлоковъ"
    admin.company.sdvf_org_inn = "7701234567"
    cp = make_counterparty(db_session)  # без ИНН
    db_session.commit()
    order = _make_order(client, headers, warehouse, variant, cp)

    resp = client.post(
        f"/orders/{order['id']}/generate-invoice",
        headers=headers,
        json={"lines": [{"order_line_id": order["lines"][0]["id"], "price": 350}]},
    )
    assert resp.status_code == 400
    assert "инн" in resp.json()["detail"].lower()


def test_generate_invoice_requires_price_for_every_line(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    admin.company.sdvf_org_naming = "ООО Щёлоковъ"
    admin.company.sdvf_org_inn = "7701234567"
    cp = make_counterparty(db_session)
    cp.inn = "7801234567"
    db_session.commit()
    order = _make_order(client, headers, warehouse, variant, cp)

    resp = client.post(f"/orders/{order['id']}/generate-invoice", headers=headers, json={"lines": []})
    assert resp.status_code == 400
    assert "цена" in resp.json()["detail"].lower()


def _mock_sdvf_calls(monkeypatch, invoice_result=None, utd_result=None):
    monkeypatch.setattr(
        SdvfClient, "get_or_create_organization", lambda self, **kw: {"id": 5, "naming": kw["naming"], "inn": kw["inn"]}
    )
    monkeypatch.setattr(
        SdvfClient, "get_or_create_counterparty", lambda self, **kw: {"id": 8, "naming": kw["naming"], "inn": kw["inn"]}
    )
    captured = {}

    def fake_create_invoice(self, **kw):
        captured["invoice_kwargs"] = kw
        return invoice_result or {"id": 1395, "pdf_url": "https://sdvf.ru/api/integration/invoices/1395/pdf/"}

    def fake_create_utd(self, **kw):
        captured["utd_kwargs"] = kw
        return utd_result or {"id": 2198, "pdf_url": "https://sdvf.ru/api/integration/utd/2198/pdf/"}

    monkeypatch.setattr(SdvfClient, "create_invoice", fake_create_invoice)
    monkeypatch.setattr(SdvfClient, "create_utd", fake_create_utd)
    return captured


def test_generate_invoice_happy_path_saves_ref_on_order(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    captured = _mock_sdvf_calls(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    admin.company.sdvf_org_naming = "ООО Щёлоковъ"
    admin.company.sdvf_org_inn = "7701234567"
    cp = make_counterparty(db_session)
    cp.inn = "7801234567"
    db_session.commit()
    order = _make_order(client, headers, warehouse, variant, cp, quantity=10)

    resp = client.post(
        f"/orders/{order['id']}/generate-invoice",
        headers=headers,
        json={"nds": 20, "nds_type": "onTop", "lines": [{"order_line_id": order["lines"][0]["id"], "price": 350}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"id": 1395, "pdf_url": "https://sdvf.ru/api/integration/invoices/1395/pdf/"}

    line = captured["invoice_kwargs"]["lines"][0]
    assert line["quantity"] == 10
    assert line["price"] == 350
    assert line["amount"] == 3500

    order_after = client.get("/orders", headers=headers).json()[0]
    assert order_after["sdvf_invoice_ref"] == {"id": 1395, "pdf_url": "https://sdvf.ru/api/integration/invoices/1395/pdf/"}


def test_generate_utd_happy_path(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    captured = _mock_sdvf_calls(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    admin.company.sdvf_org_naming = "ООО Щёлоковъ"
    admin.company.sdvf_org_inn = "7701234567"
    cp = make_counterparty(db_session)
    cp.inn = "7801234567"
    db_session.commit()
    order = _make_order(client, headers, warehouse, variant, cp, quantity=5)

    resp = client.post(
        f"/orders/{order['id']}/generate-utd",
        headers=headers,
        json={"lines": [{"order_line_id": order["lines"][0]["id"], "price": 400}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == 2198
    assert captured["utd_kwargs"]["lines"][0]["amount"] == 2000


def test_generate_invoice_wraps_sdvf_error_as_502(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    admin.company.sdvf_org_naming = "ООО Щёлоковъ"
    admin.company.sdvf_org_inn = "7701234567"
    cp = make_counterparty(db_session)
    cp.inn = "7801234567"
    db_session.commit()
    order = _make_order(client, headers, warehouse, variant, cp)

    def raise_error(self, **kw):
        raise SdvfError("СДВФ недоступен")

    monkeypatch.setattr(SdvfClient, "get_or_create_organization", raise_error)

    resp = client.post(
        f"/orders/{order['id']}/generate-invoice",
        headers=headers,
        json={"lines": [{"order_line_id": order["lines"][0]["id"], "price": 350}]},
    )
    assert resp.status_code == 502


class _FakePdfResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


def test_sdvf_pdf_404_when_not_generated_yet(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)
    order = _make_order(client, headers, warehouse, variant, cp)

    resp = client.get(f"/orders/{order['id']}/sdvf-pdf", headers=headers, params={"doc": "invoice"})
    assert resp.status_code == 404


def test_sdvf_pdf_rejects_invalid_doc_param(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)
    order = _make_order(client, headers, warehouse, variant, cp)

    resp = client.get(f"/orders/{order['id']}/sdvf-pdf", headers=headers, params={"doc": "something-else"})
    assert resp.status_code == 400


def test_sdvf_pdf_proxies_bytes_and_sends_api_key_not_visible_to_client(client, db_session, monkeypatch):
    # Ключевая регрессия: раньше фронтенд получал прямую ссылку на СДВФ, которая
    # требует X-API-Key — у браузера его нет и быть не должно (секрет интеграции
    # не должен покидать бэкенд). Теперь бэкенд сам ходит за PDF и отдаёт байты.
    _configure_sdvf(monkeypatch)
    monkeypatch.setattr(settings, "sdvf_api_key", "server-side-secret")
    captured = {}

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        captured["url"] = url
        captured["headers"] = headers
        return _FakePdfResponse(200, content=b"%PDF-1.7 fake pdf bytes")

    monkeypatch.setattr(httpx, "get", fake_get)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    warehouse, product, variant = _setup_catalog(client, headers)
    cp = make_counterparty(db_session)
    cp.inn = "7801234567"
    db_session.commit()
    order = _make_order(client, headers, warehouse, variant, cp)

    _mock_sdvf_calls(monkeypatch)
    admin.company.sdvf_org_naming = "ООО Щёлоковъ"
    admin.company.sdvf_org_inn = "7701234567"
    db_session.commit()

    gen_resp = client.post(
        f"/orders/{order['id']}/generate-invoice",
        headers=headers,
        json={"lines": [{"order_line_id": order["lines"][0]["id"], "price": 350}]},
    )
    assert gen_resp.status_code == 200, gen_resp.text

    resp = client.get(f"/orders/{order['id']}/sdvf-pdf", headers=headers, params={"doc": "invoice"})
    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.7 fake pdf bytes"
    assert resp.headers["content-type"] == "application/pdf"
    # X-API-Key ушёл на СДВФ сервер-ту-серверу, а не пользователю в браузер —
    # ответ клиенту не содержит ни ключа, ни заголовка с ним.
    assert captured["headers"]["X-API-Key"] == "server-side-secret"
    assert "server-side-secret" not in str(resp.headers)
