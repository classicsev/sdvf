from datetime import datetime, timedelta

from app.models import Integration, RoleEnum
from app.routers import automation as automation_router
from tests.conftest import auth_headers, make_account, make_company, make_user


class _FakeTBankClient:
    calls = []

    def __init__(self, base_url, token):
        pass

    def fetch_all_operations(self, account_number, date_from, date_to=None):
        _FakeTBankClient.calls.append((account_number, date_from, date_to))
        return iter(
            [
                {
                    "operationId": f"op-{len(_FakeTBankClient.calls)}",
                    "typeOfOperation": "Credit",
                    "accountAmount": 1000.00,
                    "operationDate": "2026-06-01T00:00:00Z",
                    "payer": {"name": "Плательщик"},
                }
            ]
        )


def _setup_synced_integration(client, headers, db_session, account):
    """Интеграция подключена И уже один раз синкана вручную — только так у неё
    появляется account_id, нужный автосинку (см. routers/automation.py)."""
    client.get("/integrations", headers=headers)
    integration = db_session.query(Integration).filter(Integration.provider == "tinkoff").first()
    client.post(f"/integrations/{integration.id}/connect", headers=headers, json={"token": "tok"})
    client.post(
        f"/integrations/{integration.id}/sync",
        headers=headers,
        json={"account_id": account.id, "date_from": "2026-06-01", "date_to": "2026-06-01"},
    )
    db_session.refresh(integration)
    return integration


def test_manual_sync_remembers_account_id(client, db_session, monkeypatch):
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")

    integration = _setup_synced_integration(client, headers, db_session, account)
    assert integration.account_id == account.id


def test_sync_all_skips_integration_never_manually_synced(client, db_session, monkeypatch):
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    client.get("/integrations", headers=headers)
    integration = db_session.query(Integration).filter(Integration.provider == "tinkoff").first()
    client.post(f"/integrations/{integration.id}/connect", headers=headers, json={"token": "tok"})

    resp = client.post("/integrations/sync-all", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_integrations"] == 1
    assert body["processed"] == 0
    assert body["skipped"] == 1
    assert body["skipped_rate_limited"] == 0


def test_sync_all_respects_rate_limit(client, db_session, monkeypatch):
    _FakeTBankClient.calls = []
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    integration = _setup_synced_integration(client, headers, db_session, account)
    # только что синкали (autosync_interval_minutes по умолчанию 60) — вызов без
    # force должен быть мгновенно пропущен, не сходив в "банк"
    calls_before = len(_FakeTBankClient.calls)

    resp = client.post("/integrations/sync-all", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["processed"] == 0
    assert body["skipped_rate_limited"] == 1
    assert len(_FakeTBankClient.calls) == calls_before  # в "банк" не ходили


def test_sync_all_force_ignores_rate_limit(client, db_session, monkeypatch):
    _FakeTBankClient.calls = []
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    _setup_synced_integration(client, headers, db_session, account)
    calls_before = len(_FakeTBankClient.calls)

    resp = client.post("/integrations/sync-all", params={"force": True}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["processed"] == 1
    assert body["skipped_rate_limited"] == 0
    assert len(_FakeTBankClient.calls) == calls_before + 1


def test_sync_all_processes_due_integration_incrementally(client, db_session, monkeypatch):
    _FakeTBankClient.calls = []
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    integration = _setup_synced_integration(client, headers, db_session, account)

    # Интервал истёк — следующий вызов без force тоже должен реально синкнуть
    integration.last_sync_at = datetime.utcnow() - timedelta(minutes=integration.autosync_interval_minutes + 1)
    db_session.commit()

    resp = client.post("/integrations/sync-all", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["processed"] == 1
    assert body["skipped_rate_limited"] == 0
    # date_from — с прошлого синка (с суточным нахлёстом), не вся история
    last_call = _FakeTBankClient.calls[-1]
    assert last_call[1] is not None


def test_sync_all_scoped_to_accessible_companies_only(client, db_session, monkeypatch):
    _FakeTBankClient.calls = []
    monkeypatch.setattr(automation_router, "TBankClient", _FakeTBankClient)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, account_number="40702810900000012345")
    _setup_synced_integration(client, headers, db_session, account)

    other_company = make_company(db_session, name="Чужая")
    other_admin = make_user(db_session, RoleEnum.admin, company_id=other_company.id)
    other_account = make_account(db_session, account_number="40702810900000099999", company_id=other_company.id)
    _setup_synced_integration(client, auth_headers(other_admin), db_session, other_account)

    resp = client.post("/integrations/sync-all", params={"force": True}, headers=headers)
    assert resp.status_code == 200, resp.text
    # Только своя интеграция — не чужая
    assert resp.json()["total_integrations"] == 1


def test_sync_all_non_admin_rejected(client, db_session):
    # Тот же контур прав, что и у остальных /integrations/* — доступ только
    # admin. Фронтенд обязан не дёргать sync-all автоматически для не-admin
    # пользователей (см. Transactions.jsx/Reference.jsx: гейт по роли перед
    # авто-вызовом на открытии страницы), иначе у них on-load будет падать 403.
    viewer = make_user(db_session, RoleEnum.viewer)
    resp = client.post("/integrations/sync-all", headers=auth_headers(viewer))
    assert resp.status_code == 403
