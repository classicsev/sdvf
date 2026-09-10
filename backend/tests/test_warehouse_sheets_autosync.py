from unittest.mock import patch

from app.models import RoleEnum, WarehouseSheetConnection
from app.scheduler import sync_all_warehouse_sheets
from tests.conftest import make_company, make_user


def _make_connection(db_session, company_id, is_connected=True):
    conn = WarehouseSheetConnection(company_id=company_id, is_connected=is_connected)
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return conn


def test_sync_all_warehouse_sheets_processes_every_connected_company(db_session):
    """Раньше синк запускался только кнопкой "Синхронизировать сейчас" —
    если никто не заходил на страницу Склада, реальные правки в таблице
    неделями не попадали в приложение незаметно (см. HANDOVER.md,
    "Автосинк Google-таблицы склада"). Джоб должен обработать ВСЕ
    подключённые компании разом, без привязки к конкретному пользователю."""
    admin = make_user(db_session, RoleEnum.admin)
    company1 = make_company(db_session, name="Компания 1")
    company2 = make_company(db_session, name="Компания 2")
    conn1 = _make_connection(db_session, company1.id)
    conn2 = _make_connection(db_session, company2.id)
    _make_connection(db_session, make_company(db_session, name="Компания 3").id, is_connected=False)

    with patch("app.routers.warehouse_sync.sync_connection", return_value=(True, [])) as mocked:
        processed = sync_all_warehouse_sheets(db_session)

    assert processed == 2
    assert mocked.call_count == 2
    synced_conn_ids = {call.args[1].id for call in mocked.call_args_list}
    assert synced_conn_ids == {conn1.id, conn2.id}


def test_sync_all_warehouse_sheets_one_failure_does_not_block_others(db_session):
    """Один сбойный поход в Google (недоступен сервис-аккаунт, протух
    токен и т.п.) не должен останавливать синк остальных подключённых
    компаний в том же проходе джоба."""
    make_user(db_session, RoleEnum.admin)
    company1 = make_company(db_session, name="Компания 1")
    company2 = make_company(db_session, name="Компания 2")
    _make_connection(db_session, company1.id)
    _make_connection(db_session, company2.id)

    with patch(
        "app.routers.warehouse_sync.sync_connection", side_effect=[Exception("боты, недоступен Google"), (True, [])]
    ):
        processed = sync_all_warehouse_sheets(db_session)

    assert processed == 1


def test_sync_all_warehouse_sheets_respects_rate_limit(db_session):
    """sync_connection сам решает, пропускать ли по таймеру (force=False) —
    джоб просто честно передаёт это решение в счётчик processed."""
    make_user(db_session, RoleEnum.admin)
    company = make_company(db_session, name="Компания")
    _make_connection(db_session, company.id)

    with patch("app.routers.warehouse_sync.sync_connection", return_value=(False, [])):
        processed = sync_all_warehouse_sheets(db_session)

    assert processed == 0
