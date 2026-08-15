from unittest.mock import patch

from app.config import settings
from app.models import Company, Counterparty, CounterpartyContact, RoleEnum
from tests.conftest import auth_headers, make_company, make_counterparty, make_user

SDVF_ITEMS = [
    {
        "id": 5,
        "naming": "Бурнашева Екатерина Германовна",
        "inn": "650801155621",
        "kpp": None,
        "ogrn": "311650412600020",
        "address": "г Южно-Сахалинск",
        "phone": "+79990000000",
    },
    {
        "id": 7,
        "naming": 'ООО "Дальрыба"',
        "inn": "2536000001",
        "kpp": "253601001",
        "ogrn": "1022501000001",
        "address": "г Владивосток",
        "phone": None,
    },
]


def _setup_company_with_inn(db_session, inn="2502070090"):
    admin = make_user(db_session, RoleEnum.admin)
    company = db_session.get(Company, admin.company_id)
    company.sdvf_org_inn = inn
    db_session.commit()
    return admin


def _configure_sdvf(monkeypatch):
    monkeypatch.setattr(settings, "sdvf_base_url", "https://sdvf.test")
    monkeypatch.setattr(settings, "sdvf_api_key", "test-key")


def test_sync_pulls_new_counterparties_from_sdvf(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=SDVF_ITEMS):
        resp = client.post("/counterparties/sync-sdvf", headers=auth_headers(admin))

    assert resp.status_code == 200, resp.text
    assert resp.json()["linked_by_inn"] == 2

    created = db_session.query(Counterparty).filter(Counterparty.inn == "2536000001").first()
    assert created.name == 'ООО "Дальрыба"'
    assert created.kpp == "253601001"
    assert created.sdvf_buyer_id == 7
    assert created.sdvf_synced_at is not None


def test_sync_links_existing_by_inn_and_sdvf_data_wins(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    local = make_counterparty(db_session, name="Дальрыба (из амо)")
    local.inn = "2536000001"
    db_session.commit()

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=SDVF_ITEMS):
        resp = client.post("/counterparties/sync-sdvf", headers=auth_headers(admin))

    assert resp.status_code == 200
    assert resp.json()["updated_from_sdvf"] == 1

    db_session.refresh(local)
    # СДВФ первичен — название и реквизиты приезжают оттуда, дубль не создаётся
    assert local.name == 'ООО "Дальрыба"'
    assert local.sdvf_buyer_id == 7
    assert db_session.query(Counterparty).filter(Counterparty.inn == "2536000001").count() == 1


def test_sync_create_missing_pushes_local_to_sdvf(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    local = make_counterparty(db_session, name="Только в Учёте")
    local.inn = "7707083893"
    db_session.commit()

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=[]), patch(
        "app.integrations.sdvf.SdvfClient.get_or_create_counterparty",
        return_value={"id": 42, "naming": "Только в Учёте", "inn": "7707083893", "created": True},
    ) as mock_create:
        resp = client.post(
            "/counterparties/sync-sdvf", params={"create_missing": True}, headers=auth_headers(admin)
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["created_in_sdvf"] == 1
    # organization_inn обязателен — иначе карточка уйдёт служебному пользователю СДВФ
    assert mock_create.call_args.kwargs["organization_inn"] == "2502070090"

    db_session.refresh(local)
    assert local.sdvf_buyer_id == 42


def test_sync_skips_counterparties_without_inn(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    make_counterparty(db_session, name="Без ИНН")

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=[]):
        resp = client.post(
            "/counterparties/sync-sdvf", params={"create_missing": True}, headers=auth_headers(admin)
        )

    assert resp.status_code == 200
    assert resp.json()["skipped_no_inn"] == 1
    assert resp.json()["created_in_sdvf"] == 0


def test_sync_reports_failed_card_without_aborting_rest(client, db_session, monkeypatch):
    from app.integrations.sdvf import SdvfError

    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    bad = make_counterparty(db_session, name="Кривой ИНН")
    bad.inn = "1111111111"
    good = make_counterparty(db_session, name="Нормальный")
    good.inn = "7707083893"
    db_session.commit()

    def _create(**kwargs):
        if kwargs["inn"] == "1111111111":
            raise SdvfError("СДВФ вернул 400: ИНН не прошёл проверку")
        return {"id": 43, "naming": kwargs["naming"], "inn": kwargs["inn"], "created": True}

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=[]), patch(
        "app.integrations.sdvf.SdvfClient.get_or_create_counterparty", side_effect=_create
    ):
        resp = client.post(
            "/counterparties/sync-sdvf", params={"create_missing": True}, headers=auth_headers(admin)
        )

    body = resp.json()
    assert body["failed"] == 1
    assert body["created_in_sdvf"] == 1  # вторая карточка всё равно ушла
    assert "Кривой ИНН" in body["errors"][0]


def test_sync_requires_company_org_inn(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = make_user(db_session, RoleEnum.admin)  # без sdvf_org_inn

    resp = client.post("/counterparties/sync-sdvf", headers=auth_headers(admin))
    assert resp.status_code == 400
    assert "ИНН организации" in resp.json()["detail"]


def test_sync_503_when_sdvf_not_configured(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "sdvf_base_url", "")
    monkeypatch.setattr(settings, "sdvf_api_key", "")
    admin = _setup_company_with_inn(db_session)

    resp = client.post("/counterparties/sync-sdvf", headers=auth_headers(admin))
    assert resp.status_code == 503


def test_link_to_sdvf_pulls_requisites(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    local = make_counterparty(db_session, name="Локальная карточка")

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=SDVF_ITEMS):
        resp = client.post(
            f"/counterparties/{local.id}/link-sdvf", headers=auth_headers(admin), json={"sdvf_buyer_id": 7}
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["kpp"] == "253601001"
    assert resp.json()["sdvf_buyer_id"] == 7


def test_link_rejects_card_already_linked_to_another(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    first = make_counterparty(db_session, name="Первый")
    first.sdvf_buyer_id = 7
    second = make_counterparty(db_session, name="Второй")
    db_session.commit()

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=SDVF_ITEMS):
        resp = client.post(
            f"/counterparties/{second.id}/link-sdvf", headers=auth_headers(admin), json={"sdvf_buyer_id": 7}
        )

    assert resp.status_code == 400
    assert "Первый" in resp.json()["detail"]


def test_list_sdvf_counterparties_marks_linked(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    linked = make_counterparty(db_session, name="Уже связан")
    linked.sdvf_buyer_id = 5
    db_session.commit()

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=SDVF_ITEMS):
        resp = client.get("/sdvf/counterparties", headers=auth_headers(admin))

    assert resp.status_code == 200, resp.text
    by_id = {i["id"]: i for i in resp.json()}
    assert by_id[5]["linked_counterparty_id"] == linked.id
    assert by_id[7]["linked_counterparty_id"] is None


def test_create_in_sdvf_requires_inn(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    local = make_counterparty(db_session, name="Без ИНН")

    resp = client.post(f"/counterparties/{local.id}/create-in-sdvf", headers=auth_headers(admin))
    assert resp.status_code == 400
    assert "ИНН" in resp.json()["detail"]


def test_sync_does_not_touch_other_company(client, db_session, monkeypatch):
    _configure_sdvf(monkeypatch)
    admin = _setup_company_with_inn(db_session)
    other_company = make_company(db_session, name="Чужая")
    other_cp = make_counterparty(db_session, name="Чужой контрагент", company_id=other_company.id)
    other_cp.inn = "2536000001"
    db_session.commit()

    with patch("app.integrations.sdvf.SdvfClient.list_counterparties", return_value=SDVF_ITEMS):
        client.post("/counterparties/sync-sdvf", headers=auth_headers(admin))

    db_session.refresh(other_cp)
    # Карточка чужой компании не должна быть тронута синком
    assert other_cp.name == "Чужой контрагент"
    assert other_cp.sdvf_buyer_id is None


# --- контактные лица ---


def test_contact_crud_under_counterparty(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    counterparty = make_counterparty(db_session, name="ООО Ромашка")

    resp = client.post(
        f"/counterparties/{counterparty.id}/contacts",
        headers=auth_headers(admin),
        json={"full_name": "Петров Пётр", "position": "Снабженец", "phone": "+79990001122"},
    )
    assert resp.status_code == 200, resp.text
    contact_id = resp.json()["id"]
    assert resp.json()["counterparty_id"] == counterparty.id

    resp = client.patch(
        f"/counterparty-contacts/{contact_id}",
        headers=auth_headers(admin),
        json={"full_name": "Петров Пётр Петрович", "is_primary": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_primary"] is True

    # Контакты видны в карточке контрагента
    resp = client.get("/counterparties", headers=auth_headers(admin))
    card = next(c for c in resp.json() if c["id"] == counterparty.id)
    assert [c["full_name"] for c in card["contacts"]] == ["Петров Пётр Петрович"]

    resp = client.delete(f"/counterparty-contacts/{contact_id}", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert db_session.query(CounterpartyContact).count() == 0


def test_cannot_add_contact_to_other_company_counterparty(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    other_company = make_company(db_session, name="Чужая")
    foreign = make_counterparty(db_session, name="Чужой", company_id=other_company.id)

    resp = client.post(
        f"/counterparties/{foreign.id}/contacts",
        headers=auth_headers(admin),
        json={"full_name": "Кто-то"},
    )
    assert resp.status_code == 404
