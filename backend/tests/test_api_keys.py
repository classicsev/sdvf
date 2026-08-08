from app.models import ApiKey, RoleEnum
from tests.conftest import auth_headers, make_user


def test_create_api_key_returns_plaintext_once(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post("/api-keys", headers=headers, json={"name": "1С интеграция"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["key"].startswith("fp_")
    assert data["key_prefix"] == data["key"][:10]
    assert data["user_id"] == admin.id

    listed = client.get("/api-keys", headers=headers).json()
    assert len(listed) == 1
    assert "key" not in listed[0]
    assert "key_hash" not in listed[0]


def test_api_key_authenticates_as_bound_user(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    created = client.post("/api-keys", headers=headers, json={"name": "script"}).json()
    raw_key = created["key"]

    resp = client.get("/auth/me", headers={"X-API-Key": raw_key})
    assert resp.status_code == 200
    assert resp.json()["id"] == admin.id

    key_row = db_session.get(ApiKey, created["id"])
    assert key_row.last_used_at is not None


def test_invalid_or_missing_api_key_rejected(client, db_session):
    resp = client.get("/auth/me", headers={"X-API-Key": "fp_totally_bogus"})
    assert resp.status_code == 401

    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_revoked_api_key_no_longer_works(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    created = client.post("/api-keys", headers=headers, json={"name": "temp"}).json()
    raw_key = created["key"]

    assert client.get("/auth/me", headers={"X-API-Key": raw_key}).status_code == 200

    resp = client.delete(f"/api-keys/{created['id']}", headers=headers)
    assert resp.status_code == 200

    assert client.get("/auth/me", headers={"X-API-Key": raw_key}).status_code == 401


def test_non_admin_cannot_manage_api_keys(client, db_session):
    viewer = make_user(db_session, RoleEnum.viewer)
    headers = auth_headers(viewer)

    assert client.get("/api-keys", headers=headers).status_code == 403
    assert client.post("/api-keys", headers=headers, json={"name": "x"}).status_code == 403


def test_admin_can_issue_key_for_another_user(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    operator = make_user(db_session, RoleEnum.operator, email="op@test.local")
    headers = auth_headers(admin)

    created = client.post(
        "/api-keys", headers=headers, json={"name": "for operator", "user_id": operator.id}
    ).json()
    assert created["user_id"] == operator.id

    resp = client.get("/auth/me", headers={"X-API-Key": created["key"]})
    assert resp.status_code == 200
    assert resp.json()["id"] == operator.id
