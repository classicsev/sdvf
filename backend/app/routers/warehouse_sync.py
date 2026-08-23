import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids,
    resolve_write_company_id,
)
from app.database import get_db
from app.models import RoleEnum, User, WarehouseSheetConnection, WarehouseSheetTab
from app.schemas import (
    WarehouseSheetConnectionIn,
    WarehouseSheetConnectionOut,
    WarehouseSheetSyncAllResult,
    WarehouseSheetSyncResult,
    WarehouseSheetTabIn,
    WarehouseSheetTabOut,
)
from app.routers.warehouse import compute_balances
from app.warehouse_sheets import export_balances, store_credentials, sync_tab, update_ostatok_balance

router = APIRouter(prefix="/warehouse/sheets", tags=["warehouse-sheets"])

WAREHOUSE_EDITORS = [RoleEnum.admin, RoleEnum.warehouse_operator]
ADMIN_ONLY = [RoleEnum.admin]
WAREHOUSE_MODULE = Depends(require_module("warehouse"))


def _tab_out(tab: WarehouseSheetTab) -> WarehouseSheetTabOut:
    return WarehouseSheetTabOut(
        id=tab.id,
        connection_id=tab.connection_id,
        spreadsheet_id=tab.spreadsheet_id,
        spreadsheet_label=tab.spreadsheet_label,
        tab_name=tab.tab_name,
        format=tab.format,
        product_id=tab.product_id,
        default_warehouse_id=tab.default_warehouse_id,
        column_mapping=json.loads(tab.column_mapping_json) if tab.column_mapping_json else {},
        last_synced_row=tab.last_synced_row,
        is_active=tab.is_active,
    )


def _get_connection(db: Session, user: User, company_id: str) -> WarehouseSheetConnection:
    conn = db.query(WarehouseSheetConnection).filter(WarehouseSheetConnection.company_id == company_id).first()
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Подключение к Google Таблицам не настроено")
    return conn


@router.get("/connection", response_model=Optional[WarehouseSheetConnectionOut], dependencies=[WAREHOUSE_MODULE])
def get_connection(company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = resolve_write_company_id(db, user, company_id, WAREHOUSE_EDITORS)
    return db.query(WarehouseSheetConnection).filter(WarehouseSheetConnection.company_id == target).first()


@router.post("/connection", response_model=WarehouseSheetConnectionOut, dependencies=[WAREHOUSE_MODULE])
def upsert_connection(
    payload: WarehouseSheetConnectionIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    try:
        encrypted = store_credentials(payload.credentials_json)
    except (ValueError, json.JSONDecodeError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err) or "Некорректный JSON-ключ")

    conn = db.query(WarehouseSheetConnection).filter(WarehouseSheetConnection.company_id == target).first()
    if conn is None:
        conn = WarehouseSheetConnection(company_id=target, created_by=user.id)
        db.add(conn)
    conn.credentials_encrypted = encrypted
    conn.is_connected = True
    conn.autosync_interval_minutes = payload.autosync_interval_minutes
    db.commit()
    db.refresh(conn)
    log_action(db, user, action="update", entity_type="warehouse_sheet_connection", entity_id=conn.id, company_id=target)
    return conn


@router.get("/tabs", response_model=list[WarehouseSheetTabOut], dependencies=[WAREHOUSE_MODULE])
def list_tabs(company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = resolve_write_company_id(db, user, company_id, WAREHOUSE_EDITORS)
    conn = db.query(WarehouseSheetConnection).filter(WarehouseSheetConnection.company_id == target).first()
    if conn is None:
        return []
    tabs = db.query(WarehouseSheetTab).filter(WarehouseSheetTab.connection_id == conn.id).all()
    return [_tab_out(t) for t in tabs]


@router.post("/tabs", response_model=WarehouseSheetTabOut, dependencies=[WAREHOUSE_MODULE])
def create_tab(
    payload: WarehouseSheetTabIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    conn = _get_connection(db, user, target)
    tab = WarehouseSheetTab(
        connection_id=conn.id,
        spreadsheet_id=payload.spreadsheet_id,
        spreadsheet_label=payload.spreadsheet_label,
        tab_name=payload.tab_name,
        format=payload.format,
        product_id=payload.product_id,
        default_warehouse_id=payload.default_warehouse_id,
        column_mapping_json=json.dumps(payload.column_mapping, ensure_ascii=False) if payload.column_mapping else None,
        is_active=payload.is_active,
    )
    db.add(tab)
    db.commit()
    db.refresh(tab)
    log_action(db, user, action="create", entity_type="warehouse_sheet_tab", entity_id=tab.id, company_id=target)
    return _tab_out(tab)


@router.patch("/tabs/{tab_id}", response_model=WarehouseSheetTabOut, dependencies=[WAREHOUSE_MODULE])
def update_tab(
    tab_id: str, payload: WarehouseSheetTabIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    accessible = get_accessible_company_ids(db, user)
    tab = db.get(WarehouseSheetTab, tab_id)
    if tab is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лист не найден")
    conn = db.get(WarehouseSheetConnection, tab.connection_id)
    if conn.company_id not in accessible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лист не найден")
    check_company_role(db, user, conn.company_id, ADMIN_ONLY)

    tab.spreadsheet_id = payload.spreadsheet_id
    tab.spreadsheet_label = payload.spreadsheet_label
    tab.tab_name = payload.tab_name
    tab.format = payload.format
    tab.product_id = payload.product_id
    tab.default_warehouse_id = payload.default_warehouse_id
    tab.column_mapping_json = json.dumps(payload.column_mapping, ensure_ascii=False) if payload.column_mapping else None
    tab.is_active = payload.is_active
    db.commit()
    db.refresh(tab)
    return _tab_out(tab)


@router.delete("/tabs/{tab_id}", dependencies=[WAREHOUSE_MODULE])
def delete_tab(tab_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    accessible = get_accessible_company_ids(db, user)
    tab = db.get(WarehouseSheetTab, tab_id)
    if tab is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лист не найден")
    conn = db.get(WarehouseSheetConnection, tab.connection_id)
    if conn.company_id not in accessible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лист не найден")
    check_company_role(db, user, conn.company_id, ADMIN_ONLY)
    db.delete(tab)
    db.commit()
    return {"deleted": True}


@router.get("/tabs/{tab_id}/preview", dependencies=[WAREHOUSE_MODULE])
def preview_tab(tab_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    accessible = get_accessible_company_ids(db, user)
    tab = db.get(WarehouseSheetTab, tab_id)
    if tab is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лист не найден")
    conn = db.get(WarehouseSheetConnection, tab.connection_id)
    if conn.company_id not in accessible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лист не найден")
    check_company_role(db, user, conn.company_id, WAREHOUSE_EDITORS)
    try:
        result = sync_tab(db, conn, tab, dry_run=True)
    except Exception as err:  # ошибки Google API/сети — не должны выглядеть как 500 без объяснения
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Не удалось прочитать таблицу: {err}")
    return result


@router.post("/sync-all", response_model=WarehouseSheetSyncAllResult, dependencies=[WAREHOUSE_MODULE])
def sync_all(
    company_id: Optional[str] = None,
    force: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Без отдельного планировщика/крона — тот же ленивый паттерн, что и
    automation.py::sync_all_integrations: реально идём в Google не чаще
    connection.autosync_interval_minutes, если не force=True (кнопка
    "Синхронизировать сейчас")."""
    company_ids = resolve_company_ids(db, user, company_id)
    connections = db.query(WarehouseSheetConnection).filter(
        WarehouseSheetConnection.company_id.in_(company_ids), WarehouseSheetConnection.is_connected.is_(True)
    ).all()

    now = datetime.utcnow()
    processed = 0
    skipped_rate_limited = 0
    results: list[WarehouseSheetSyncResult] = []

    for conn in connections:
        if not force and conn.last_sync_at:
            elapsed_minutes = (now - conn.last_sync_at).total_seconds() / 60
            if elapsed_minutes < conn.autosync_interval_minutes:
                skipped_rate_limited += 1
                continue

        tabs = db.query(WarehouseSheetTab).filter(
            WarehouseSheetTab.connection_id == conn.id, WarehouseSheetTab.is_active.is_(True)
        ).all()
        spreadsheet_ids_for_balances: set[str] = set()
        for tab in tabs:
            try:
                r = sync_tab(db, conn, tab, dry_run=False)
                results.append(WarehouseSheetSyncResult(**r))
                if tab.format.value == "movements":
                    spreadsheet_ids_for_balances.add(tab.spreadsheet_id)
            except Exception as err:
                results.append(WarehouseSheetSyncResult(tab_id=tab.id, tab_name=tab.tab_name, imported=0, error=str(err)))

        for spreadsheet_id in spreadsheet_ids_for_balances:
            try:
                export_balances(db, conn, spreadsheet_id, conn.company_id)
            except Exception:
                pass  # остатки — вторичный эффект, не должны валить весь синк движений
            try:
                update_ostatok_balance(db, conn, spreadsheet_id, conn.company_id)
            except Exception:
                pass  # аналогично — лист "ОСТАТОК"/"Месяц" не обязаны существовать везде

        conn.last_sync_at = now
        db.add(conn)
        db.commit()
        processed += 1

    message = f"Синхронизировано подключений: {processed} из {len(connections)}"
    if skipped_rate_limited:
        message += f", пропущено по таймеру: {skipped_rate_limited}"
    return WarehouseSheetSyncAllResult(
        processed=processed, skipped_rate_limited=skipped_rate_limited, results=results, message=message
    )


@router.get("/balance-as-of", dependencies=[WAREHOUSE_MODULE])
def balance_as_of(
    year: int,
    month: int,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Остаток накопительно на конец указанного месяца — для месячного среза
    в реальной Google-таблице (лист "ОСТАТОК"), дёргается из Apps Script по
    API-ключу вместо ненадёжных SUMIFS-формул на месте (см. HANDOVER.md,
    2026-08-23 — прямая попытка формулами разошлась с реальными данными)."""
    import calendar
    from datetime import date as date_type

    company_ids = resolve_company_ids(db, user, company_id)
    if not (1 <= month <= 12):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Месяц должен быть от 1 до 12")
    last_day = calendar.monthrange(year, month)[1]
    as_of = date_type(year, month, last_day)
    balances = compute_balances(db, company_ids, include_empty=True, as_of_date=as_of)
    return [
        {
            "warehouse_name": b.warehouse_name,
            "product_name": b.product_name,
            "variant_name": b.variant_name,
            "quantity": float(b.quantity),
        }
        for b in balances
    ]
