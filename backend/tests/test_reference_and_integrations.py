from app.models import Integration, RoleEnum
from tests.conftest import auth_headers, make_user


def test_malformed_uuid_on_reference_endpoints_returns_404(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    for resource in ("categories", "projects", "accounts", "counterparties"):
        resp = client.patch(f"/{resource}/not-a-uuid", headers=headers, json={"name": "x", "type": "expense"})
        assert resp.status_code == 404, f"{resource} PATCH should 404, got {resp.status_code}"

        resp = client.delete(f"/{resource}/not-a-uuid", headers=headers)
        assert resp.status_code == 404, f"{resource} DELETE should 404, got {resp.status_code}"


def test_non_admin_cannot_write_reference_data(client, db_session):
    viewer = make_user(db_session, RoleEnum.viewer)
    resp = client.post("/categories", headers=auth_headers(viewer), json={"name": "x", "type": "expense"})
    assert resp.status_code == 403


def test_integrations_catalog_lazily_seeded_and_no_credentials_leak(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.get("/integrations", headers=auth_headers(admin))
    assert resp.status_code == 200
    providers = {i["provider"] for i in resp.json()}
    assert "tinkoff" in providers
    assert all("credentials_encrypted" not in i for i in resp.json())


def test_connect_encrypts_token_and_disconnect_clears_it(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    client.get("/integrations", headers=headers)  # triggers lazy seed
    integration_id = db_session.query(Integration).filter(Integration.provider == "tinkoff").first().id

    resp = client.post(f"/integrations/{integration_id}/connect", headers=headers, json={"token": "my-secret-token"})
    assert resp.status_code == 200
    assert resp.json()["is_connected"] is True
    assert "credentials_encrypted" not in resp.json()

    db_session.expire_all()
    raw = db_session.get(Integration, integration_id)
    assert raw.credentials_encrypted is not None
    assert "my-secret-token" not in raw.credentials_encrypted

    resp = client.post(f"/integrations/{integration_id}/disconnect", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_connected"] is False

    db_session.expire_all()
    raw = db_session.get(Integration, integration_id)
    assert raw.credentials_encrypted is None


def test_sync_rejects_unsupported_provider(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    client.get("/integrations", headers=headers)
    ozon = db_session.query(Integration).filter(Integration.provider == "ozon").first()
    client.post(f"/integrations/{ozon.id}/connect", headers=headers, json={"token": "x"})

    from tests.conftest import make_account

    account = make_account(db_session, account_number="40702810900000012345")
    resp = client.post(
        f"/integrations/{ozon.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01"},
    )
    assert resp.status_code == 400


def test_sync_requires_account_number(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    client.get("/integrations", headers=headers)
    tinkoff = db_session.query(Integration).filter(Integration.provider == "tinkoff").first()
    client.post(f"/integrations/{tinkoff.id}/connect", headers=headers, json={"token": "TBankSandboxToken"})

    from tests.conftest import make_account

    account = make_account(db_session)  # без account_number
    resp = client.post(
        f"/integrations/{tinkoff.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01"},
    )
    assert resp.status_code == 400
    assert "номер счёта" in resp.json()["detail"]
