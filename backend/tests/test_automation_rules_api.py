from app.models import RoleEnum
from tests.conftest import auth_headers, make_user


def test_rule_full_crud(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.post(
        "/automation-rules",
        headers=headers,
        json={
            "condition_json": {"field": "amount", "op": "gt", "value": 1000},
            "action_json": {"set_category": "cat-1"},
        },
    )
    assert resp.status_code == 200, resp.text
    rule = resp.json()
    assert rule["is_active"] is True
    assert rule["created_by"] == admin.id

    resp = client.get("/automation-rules", headers=headers)
    assert any(r["id"] == rule["id"] for r in resp.json())

    resp = client.patch(
        f"/automation-rules/{rule['id']}",
        headers=headers,
        json={
            "condition_json": {"field": "amount", "op": "gt", "value": 2000},
            "action_json": {"set_category": "cat-1"},
            "is_active": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert resp.json()["condition_json"]["value"] == 2000

    resp = client.delete(f"/automation-rules/{rule['id']}", headers=headers)
    assert resp.status_code == 200

    resp = client.get("/automation-rules", headers=headers)
    assert not any(r["id"] == rule["id"] for r in resp.json())


def test_rule_accepts_compound_condition_list(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.post(
        "/automation-rules",
        headers=auth_headers(admin),
        json={
            "condition_json": [
                {"field": "amount", "op": "lt", "value": 500},
                {"field": "comment", "op": "contains", "value": "комиссия"},
            ],
            "action_json": {"set_category": "cat-fee"},
        },
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["condition_json"], list)
    assert len(resp.json()["condition_json"]) == 2


def test_non_admin_cannot_manage_rules(client, db_session):
    operator = make_user(db_session, RoleEnum.operator)
    headers = auth_headers(operator)

    resp = client.get("/automation-rules", headers=headers)
    assert resp.status_code == 403

    resp = client.post(
        "/automation-rules",
        headers=headers,
        json={"condition_json": {"field": "amount", "op": "gt", "value": 1}, "action_json": {}},
    )
    assert resp.status_code == 403


def test_malformed_uuid_on_rule_returns_404(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    resp = client.delete("/automation-rules/not-a-uuid", headers=auth_headers(admin))
    assert resp.status_code == 404
