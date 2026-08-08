from app.models import Counterparty, Integration, RoleEnum, Transaction
from app.routers import automation as automation_router
from tests.conftest import auth_headers, make_account, make_user

CONNECT_PAYLOAD = {
    "subdomain": "mvkusno",
    "client_id": "cid",
    "client_secret": "csecret",
    "access_token": "access-1",
    "refresh_token": "refresh-1",
    "redirect_uri": "https://localhost/",
}


class _FakeAmoCrmClient:
    tokens_refreshed = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def fetch_all_contacts(self):
        return iter(
            [
                {"id": 1, "name": "ООО Мидии Омск"},
                {"id": 2, "name": "ИП Мальшин"},
                {"id": 3},  # без имени — map_contact вернёт None, должен быть пропущен
            ]
        )

    def fetch_all_leads(self, date_from=None):
        return iter(
            [
                {
                    "id": 100,
                    "name": "ТД-787",
                    "price": 21000,
                    "status_id": 142,
                    "closed_at": 1751875200,  # 2025-07-07
                    "_embedded": {"contacts": [{"id": 1}]},
                },
                {
                    "id": 101,
                    "name": "В работе",
                    "price": 5000,
                    "status_id": 39374356,  # не "успешно реализовано" — пропускается
                    "closed_at": 1751875200,
                },
                {
                    "id": 102,
                    "name": "Без суммы",
                    "price": None,
                    "status_id": 142,
                    "closed_at": 1751875200,
                },
            ]
        )


def _setup_connected_amocrm(client, headers, db_session):
    client.get("/integrations", headers=headers)  # lazy-seed каталога
    integration = db_session.query(Integration).filter(Integration.provider == "amocrm").first()
    resp = client.post(f"/integrations/{integration.id}/connect-amocrm", headers=headers, json=CONNECT_PAYLOAD)
    assert resp.status_code == 200, resp.text
    return integration


def test_connect_amocrm_stores_encrypted_credentials(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    integration = _setup_connected_amocrm(client, headers, db_session)

    db_session.refresh(integration)
    assert integration.is_connected is True
    assert integration.credentials_encrypted is not None
    # в открытом виде секрет никогда не должен светиться в ответе API
    resp = client.get("/integrations", headers=headers)
    amo = next(i for i in resp.json() if i["provider"] == "amocrm")
    assert "credentials_encrypted" not in amo


def test_sync_amocrm_creates_contacts_and_won_deal_transaction(client, db_session, monkeypatch):
    monkeypatch.setattr(automation_router, "AmoCrmClient", _FakeAmoCrmClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    integration = _setup_connected_amocrm(client, headers, db_session)

    resp = client.post(
        f"/integrations/{integration.id}/sync-amocrm",
        headers=headers,
        json={"account_id": account.id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contacts_created"] == 2
    assert body["contacts_matched"] == 0
    assert body["deals_created"] == 1
    assert body["deals_skipped"] == 2  # не "успешно реализовано" + без суммы

    cp_names = {c.name for c in db_session.query(Counterparty).all()}
    assert {"ООО Мидии Омск", "ИП Мальшин"} <= cp_names

    tx = db_session.query(Transaction).filter(Transaction.external_ref == "amocrm:100").first()
    assert tx is not None
    assert tx.type.value == "income"
    assert float(tx.amount) == 21000.0
    counterparty = db_session.get(Counterparty, tx.counterparty_id)
    assert counterparty.name == "ООО Мидии Омск"

    db_session.refresh(integration)
    assert integration.last_sync_at is not None


def test_sync_amocrm_dedupes_on_rerun(client, db_session, monkeypatch):
    monkeypatch.setattr(automation_router, "AmoCrmClient", _FakeAmoCrmClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    integration = _setup_connected_amocrm(client, headers, db_session)

    client.post(f"/integrations/{integration.id}/sync-amocrm", headers=headers, json={"account_id": account.id})
    resp = client.post(f"/integrations/{integration.id}/sync-amocrm", headers=headers, json={"account_id": account.id})

    body = resp.json()
    assert body["deals_created"] == 0
    assert body["deals_skipped"] == 3  # дубль + не-выигранная + без суммы
    assert body["contacts_created"] == 0
    assert body["contacts_matched"] == 2

    total_tx = db_session.query(Transaction).filter(Transaction.external_ref.like("amocrm:%")).count()
    assert total_tx == 1


def test_sync_amocrm_requires_connected_integration(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    client.get("/integrations", headers=headers)
    integration = db_session.query(Integration).filter(Integration.provider == "amocrm").first()

    resp = client.post(
        f"/integrations/{integration.id}/sync-amocrm", headers=headers, json={"account_id": account.id}
    )
    assert resp.status_code == 400


def test_connect_amocrm_rejects_wrong_provider(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    client.get("/integrations", headers=headers)
    tbank = db_session.query(Integration).filter(Integration.provider == "tinkoff").first()

    resp = client.post(f"/integrations/{tbank.id}/connect-amocrm", headers=headers, json=CONNECT_PAYLOAD)
    assert resp.status_code == 400


def test_sync_amocrm_fails_cleanly_on_api_error(client, db_session, monkeypatch):
    from app.integrations.amocrm import AmoCrmError

    class _FailingClient:
        tokens_refreshed = False

        def __init__(self, **kwargs):
            pass

        def fetch_all_contacts(self):
            raise AmoCrmError("amoCRM API вернул 401: токен недействителен")

        def fetch_all_leads(self, date_from=None):
            return iter([])

    monkeypatch.setattr(automation_router, "AmoCrmClient", _FailingClient)

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    integration = _setup_connected_amocrm(client, headers, db_session)

    resp = client.post(
        f"/integrations/{integration.id}/sync-amocrm", headers=headers, json={"account_id": account.id}
    )
    assert resp.status_code == 502
    db_session.refresh(integration)
    assert integration.last_sync_at is None


def test_non_admin_cannot_connect_or_sync_amocrm(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    viewer = make_user(db_session, RoleEnum.viewer)
    client.get("/integrations", headers=auth_headers(admin))
    integration = db_session.query(Integration).filter(Integration.provider == "amocrm").first()

    resp = client.post(
        f"/integrations/{integration.id}/connect-amocrm", headers=auth_headers(viewer), json=CONNECT_PAYLOAD
    )
    assert resp.status_code == 403
