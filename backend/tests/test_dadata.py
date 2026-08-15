from unittest.mock import patch

from app.config import settings
from app.integrations.dadata import DadataClient
from app.models import RoleEnum
from tests.conftest import auth_headers, make_user

LEGAL_SUGGESTION = {
    "suggestions": [
        {
            "value": 'ООО "ТИХООКЕАНСКАЯ ФАКТОРИЯ"',
            "data": {
                "inn": "2536123456",
                "kpp": "253601001",
                "ogrn": "1122536001234",
                "type": "LEGAL",
                "opf": {"short": "ООО"},
                "address": {"value": "690091, Приморский край, г Владивосток, ул Светланская, д 1"},
                "management": {"name": "Щёлоков Эдуард Олегович", "post": "Генеральный директор"},
            },
        }
    ]
}

INDIVIDUAL_SUGGESTION = {
    "suggestions": [
        {
            "value": "ИП Щёлоков Эдуард Олегович",
            "data": {
                "inn": "253601234567",
                "ogrn": "312253600012345",
                "type": "INDIVIDUAL",
                "opf": {"short": "ИП"},
                "address": {"value": "690091, Приморский край, г Владивосток"},
            },
        }
    ]
}


def _fake_response(payload, status_code=200):
    class _Resp:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return payload

    return _Resp()


def test_client_maps_legal_entity_fields():
    with patch("app.integrations.dadata.httpx.post", return_value=_fake_response(LEGAL_SUGGESTION)):
        found = DadataClient("test-key").find_by_inn("2536123456")

    assert found["name"] == 'ООО "ТИХООКЕАНСКАЯ ФАКТОРИЯ"'
    assert found["kpp"] == "253601001"
    assert found["ogrn"] == "1122536001234"
    assert found["party_type"] == "legal_entity"
    assert found["supervisor"] == "Щёлоков Эдуард Олегович"
    assert found["supervisor_position"] == "Генеральный директор"


def test_client_maps_individual_without_kpp():
    with patch("app.integrations.dadata.httpx.post", return_value=_fake_response(INDIVIDUAL_SUGGESTION)):
        found = DadataClient("test-key").find_by_inn("253601234567")

    assert found["party_type"] == "individual"
    # У ИП КПП не существует — отдаём пустую строку, а не значение из ответа
    assert found["kpp"] == ""
    assert found["supervisor"] == ""


def test_client_retries_with_explicit_type_when_first_call_empty():
    responses = [_fake_response({"suggestions": []}), _fake_response(INDIVIDUAL_SUGGESTION)]
    with patch("app.integrations.dadata.httpx.post", side_effect=responses) as mock_post:
        found = DadataClient("test-key").find_by_inn("253601234567")

    assert found is not None
    assert mock_post.call_count == 2
    assert mock_post.call_args_list[1].kwargs["json"] == {"query": "253601234567", "type": "INDIVIDUAL"}


def test_endpoint_returns_requisites(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "dadata_api_key", "test-key")
    user = make_user(db_session, RoleEnum.viewer)

    with patch("app.integrations.dadata.httpx.post", return_value=_fake_response(LEGAL_SUGGESTION)):
        resp = client.get("/dadata/party", params={"inn": "2536123456"}, headers=auth_headers(user))

    assert resp.status_code == 200, resp.text
    assert resp.json()["kpp"] == "253601001"


def test_endpoint_rejects_malformed_inn(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "dadata_api_key", "test-key")
    user = make_user(db_session, RoleEnum.viewer)

    resp = client.get("/dadata/party", params={"inn": "123"}, headers=auth_headers(user))
    assert resp.status_code == 400


def test_endpoint_404_when_not_found(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "dadata_api_key", "test-key")
    user = make_user(db_session, RoleEnum.viewer)

    with patch("app.integrations.dadata.httpx.post", return_value=_fake_response({"suggestions": []})):
        resp = client.get("/dadata/party", params={"inn": "2536123456"}, headers=auth_headers(user))

    assert resp.status_code == 404


def test_endpoint_503_when_key_not_configured(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "dadata_api_key", "")
    user = make_user(db_session, RoleEnum.viewer)

    resp = client.get("/dadata/party", params={"inn": "2536123456"}, headers=auth_headers(user))
    assert resp.status_code == 503


def test_endpoint_requires_auth(client):
    resp = client.get("/dadata/party", params={"inn": "2536123456"})
    assert resp.status_code == 401
