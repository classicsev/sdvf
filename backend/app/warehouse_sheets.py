"""Движок двусторонней синхронизации склада с Google Таблицами.

Два формата листов (см. models.py::WarehouseSheetTabFormat):

- movements — универсальный шаблон, 1 строка = 1 движение склада. Колонки
  фиксированы (см. MOVEMENTS_HEADER ниже). Поддерживает чтение и запись.
- wide_calibers_in / wide_calibers_out / processing_wide — легаси-листы
  (склад ведёт по видам, калибры/SKU по столбцам). Реальные листы пользователя
  неоднородны (дублирующиеся заголовки, несколько под-таблиц в одном листе) —
  автоматическое распознавание заголовков ненадёжно, поэтому маппинг колонок
  задаётся один раз явно, по БУКВЕ столбца, в WarehouseSheetTab.column_mapping_json:

    {
      "date_col": "A",
      "calibers": {"C": "<product_variant_id>", "D": "<product_variant_id>", ...},
      "executor_col": "I",       # для wide_calibers_in — столбец с именем "Чистил"
      "payroll_col": "N",        # для wide_calibers_in — столбец "ЗП" (итог, не ставка)
      "warehouse_col": "L",      # опционально — столбец "СКЛАД"
      "note_col": "M",           # опционально — "Примечание"/название клиента
      "marker_col": "P"          # куда писать id импортированного движения
    }

  Только чтение и дозапись новых строк в конец — обновление/удаление уже
  синхронизированных строк не поддерживается (см. план: курсор по номеру
  строки, не сопоставление по содержимому).
"""

import json
import string
from datetime import date as date_type, datetime
from typing import Optional

import gspread
from sqlalchemy.orm import Session

from app.crypto import decrypt_field, encrypt_field
from app.models import (
    Employee,
    Product,
    ProductVariant,
    StockDirectionEnum,
    Warehouse,
    WarehouseSheetConnection,
    WarehouseSheetTab,
    WarehouseSheetTabFormat,
)
from app.routers.warehouse import build_movement, compute_balances
from app.schemas import StockMovementIn

MOVEMENTS_HEADER = [
    "Дата", "Склад", "Товар", "Модификация", "Направление",
    "Количество", "Сотрудник", "Ставка ЗП", "Примечание", "ID",
]
MOVEMENTS_MARKER_COL = "J"
MOVEMENTS_DIRECTION_LABELS = {
    StockDirectionEnum.in_: "Приход",
    StockDirectionEnum.out: "Расход",
    StockDirectionEnum.adjustment: "Инвентаризация",
}
MOVEMENTS_DIRECTION_BY_LABEL = {v: k for k, v in MOVEMENTS_DIRECTION_LABELS.items()}

BALANCES_TAB_NAME = "Остатки"
BALANCES_HEADER = ["Склад", "Товар", "Модификация", "Количество", "Резерв", "Доступно", "Обновлено"]

HEADER_ROWS = 2  # во всех реальных листах пользователя — строка 1: заголовок раздела, строка 2: названия колонок


def col_letter_to_index(letter: str) -> int:
    """'A' -> 1, 'B' -> 2, ... 'AA' -> 27."""
    letter = letter.strip().upper()
    idx = 0
    for ch in letter:
        idx = idx * 26 + (string.ascii_uppercase.index(ch) + 1)
    return idx


def get_client(connection: WarehouseSheetConnection) -> gspread.Client:
    raw = decrypt_field(connection.credentials_encrypted)
    if raw is None:
        raise ValueError("Не удалось расшифровать ключ service account")
    return gspread.service_account_from_dict(json.loads(raw))


def store_credentials(credentials_json: str) -> str:
    # Валидируем, что это похоже на service-account JSON, до шифрования — иначе
    # ошибка обнаружится только при первом синке, а не сразу при сохранении.
    parsed = json.loads(credentials_json)
    if parsed.get("type") != "service_account":
        raise ValueError("Это не похоже на JSON-ключ service account Google")
    return encrypt_field(credentials_json)


def resolve_employee(db: Session, company_id: str, name: str) -> Optional[Employee]:
    if not name or not name.strip():
        return None
    needle = name.strip().lower()
    employees = db.query(Employee).filter(Employee.company_id == company_id, Employee.status == "active").all()

    def emp_aliases(emp: Employee) -> list[str]:
        return [a.strip().lower() for a in (emp.aliases or "").split(",") if a.strip()]

    for emp in employees:
        if emp.full_name.strip().lower() == needle or needle in emp_aliases(emp):
            return emp
    # Реальные листы часто пишут только имя/прозвище водолаза ("Антон"), а не
    # полное ФИО ("Антон Жаркой"), или сокращение, заведённое вручную в
    # aliases сотрудника ("Цихм" -> "Женя Цихмейструк") — ищем needle как
    # отдельное слово в ФИО или среди алиасов. Если совпало у НЕСКОЛЬКИХ
    # сотрудников сразу — не угадываем (иначе риск начислить зарплату не
    # тому), считаем нераспознанным как и при полном отсутствии совпадения.
    matches = [
        emp
        for emp in employees
        if needle in {w.lower() for w in emp.full_name.split()} or needle in emp_aliases(emp)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _cell(row: list[str], col_letter: Optional[str]) -> str:
    if not col_letter:
        return ""
    idx = col_letter_to_index(col_letter) - 1
    return row[idx] if idx < len(row) else ""


def _parse_number(raw: str) -> Optional[float]:
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


# Нижняя граница здравого смысла для дат из таблиц — строки "ИТОГО"/суммы
# внизу листов иногда несут в колонке даты результат SUM() по пустому
# диапазону, который Google форматирует как дату (напр. "28.05.1905") —
# без этой защиты такая строка ушла бы в БД как настоящее движение с
# суммарным (завышенным на порядки) количеством за "день".
MIN_SANE_DATE = date_type(2020, 1, 1)


def _parse_date(raw: str) -> Optional[date_type]:
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        if parsed < MIN_SANE_DATE:
            return None
        return parsed
    # Некоторые листы (напр. "МСК ПРИход"/"МСК РАСход") пишут дату без года —
    # "17.08". Год берём текущий календарный на момент синка: на практике
    # такие листы ведутся в реальном времени, дата всегда "в этом году".
    try:
        parsed = datetime.strptime(raw, "%d.%m").date().replace(year=datetime.utcnow().year)
    except ValueError:
        return None
    if parsed < MIN_SANE_DATE:
        return None
    return parsed


class SyncOutcome:
    """Результат одного прохода по листу. `marks` — что дописать в таблицу
    (номер строки → значение маркера), заполняется по ходу разбора и
    применяется вызывающей стороной одним batch-запросом в конце (не по
    ячейке за раз — иначе синк с сотнями строк упрётся в квоту Google API)."""

    def __init__(self):
        self.imported = 0
        self.unresolved_employees: set[str] = set()
        self.unresolved_warehouses: set[str] = set()
        self.marks: dict[int, str] = {}
        self.preview_rows: list[dict] = []
        # Все реально созданные движения этого прохода — используется, чтобы
        # тут же отдать их в push_movement_to_configured_tabs() и продублировать
        # в универсальный лист "Движения" (единый непрерывный источник по всем
        # видам сразу — основа для месячного фильтра поверх всей таблицы).
        self.created_movements: list = []

    def as_result(self, tab: WarehouseSheetTab) -> dict:
        return {
            "tab_id": tab.id,
            "tab_name": tab.tab_name,
            "imported": self.imported,
            "unresolved_employees": sorted(self.unresolved_employees),
            "unresolved_warehouses": sorted(self.unresolved_warehouses),
        }


def _process_movements_format(
    db: Session, company_id: str, rows: list[list[str]], start_row: int, dry_run: bool
) -> tuple[SyncOutcome, int]:
    outcome = SyncOutcome()
    last_row = start_row - 1
    warehouses_by_name = {
        w.name.strip().lower(): w for w in db.query(Warehouse).filter(Warehouse.company_id == company_id).all()
    }
    variants_by_key = {}
    for v in db.query(ProductVariant).filter(ProductVariant.company_id == company_id).all():
        product = db.get(Product, v.product_id)
        if product:
            variants_by_key[(product.name.strip().lower(), v.name.strip().lower())] = v

    for i, row in enumerate(rows[start_row - 1 :], start=start_row):
        if not any(c.strip() for c in row):
            continue
        last_row = i
        already_marked = (row[9] if len(row) > 9 else "").strip()
        if already_marked:
            continue

        d = _parse_date(row[0] if len(row) > 0 else "")
        warehouse = warehouses_by_name.get((row[1] if len(row) > 1 else "").strip().lower())
        variant = variants_by_key.get(
            ((row[2] if len(row) > 2 else "").strip().lower(), (row[3] if len(row) > 3 else "").strip().lower())
        )
        direction = MOVEMENTS_DIRECTION_BY_LABEL.get((row[4] if len(row) > 4 else "").strip())
        quantity = _parse_number(row[5] if len(row) > 5 else "")
        executor_name = (row[6] if len(row) > 6 else "").strip()
        payroll_rate = _parse_number(row[7] if len(row) > 7 else "")
        note = (row[8] if len(row) > 8 else "").strip() or None

        if not (d and warehouse and variant and direction and quantity):
            continue  # строка неполная/нечитаемая — пропускаем молча, не гадаем

        executor = resolve_employee(db, company_id, executor_name) if executor_name else None
        if executor_name and not executor:
            outcome.unresolved_employees.add(executor_name)
            continue

        if dry_run:
            outcome.preview_rows.append({"row": i, "date": str(d), "variant": variant.name, "quantity": quantity})
            outcome.imported += 1
            continue

        payload = StockMovementIn(
            date=d, warehouse_id=warehouse.id, product_variant_id=variant.id, direction=direction,
            quantity=quantity, note=note, executor_id=executor.id if executor else None, payroll_rate=payroll_rate,
        )
        movement = build_movement(db, company_id, payload)
        db.flush()
        outcome.marks[i] = movement.id
        outcome.created_movements.append(movement)
        outcome.imported += 1

    return outcome, last_row


def _process_wide_format(
    db: Session, company_id: str, tab: WarehouseSheetTab, rows: list[list[str]], start_row: int, dry_run: bool
) -> tuple[SyncOutcome, int]:
    cfg = json.loads(tab.column_mapping_json or "{}")
    outcome = SyncOutcome()
    last_row = start_row - 1
    default_warehouse = db.get(Warehouse, tab.default_warehouse_id) if tab.default_warehouse_id else None
    warehouses_by_name = {
        w.name.strip().lower(): w for w in db.query(Warehouse).filter(Warehouse.company_id == company_id).all()
    }
    is_processing = tab.format == WarehouseSheetTabFormat.processing_wide
    base_direction = (
        StockDirectionEnum.in_ if tab.format == WarehouseSheetTabFormat.wide_calibers_in else StockDirectionEnum.out
    )
    marker_col = cfg.get("marker_col")

    for i, row in enumerate(rows[start_row - 1 :], start=start_row):
        if not any(c.strip() for c in row):
            continue
        last_row = i
        if marker_col and _cell(row, marker_col).strip():
            continue

        d = _parse_date(_cell(row, cfg.get("date_col", "A")))
        if not d:
            continue

        warehouse_name = _cell(row, cfg.get("warehouse_col")).strip()
        if warehouse_name:
            warehouse = warehouses_by_name.get(warehouse_name.lower())
            if not warehouse:
                outcome.unresolved_warehouses.add(warehouse_name)
                continue
        else:
            warehouse = default_warehouse
            if not warehouse:
                continue
        note = _cell(row, cfg.get("note_col")).strip() or None
        executor_name = _cell(row, cfg.get("executor_col")).strip()
        payroll_total = _parse_number(_cell(row, cfg.get("payroll_col")))

        executor = resolve_employee(db, company_id, executor_name) if executor_name else None
        if executor_name and not executor:
            outcome.unresolved_employees.add(executor_name)
            continue

        row_movement_ids = []
        for col_letter, variant_id in cfg.get("calibers", {}).items():
            raw_qty = _parse_number(_cell(row, col_letter))
            if not raw_qty:
                continue
            direction = base_direction
            quantity = raw_qty
            if is_processing:
                direction = (
                    StockDirectionEnum.production_yield if raw_qty > 0 else StockDirectionEnum.production_consume
                )
                quantity = abs(raw_qty)

            payroll_rate = None
            if payroll_total and quantity and direction == StockDirectionEnum.in_:
                payroll_rate = round(payroll_total / quantity, 4)

            if dry_run:
                outcome.preview_rows.append(
                    {"row": i, "date": str(d), "variant_id": variant_id, "quantity": quantity, "direction": direction.value}
                )
                outcome.imported += 1
                continue

            payload = StockMovementIn(
                date=d, warehouse_id=warehouse.id, product_variant_id=variant_id, direction=direction,
                quantity=quantity, note=note, executor_id=executor.id if executor else None, payroll_rate=payroll_rate,
            )
            movement = build_movement(db, company_id, payload)
            db.flush()
            row_movement_ids.append(movement.id)
            outcome.created_movements.append(movement)
            outcome.imported += 1

        if row_movement_ids and not dry_run:
            outcome.marks[i] = ",".join(row_movement_ids)

    return outcome, last_row


def sync_tab(db: Session, connection: WarehouseSheetConnection, tab: WarehouseSheetTab, dry_run: bool = False) -> dict:
    gc = get_client(connection)
    sh = gc.open_by_key(tab.spreadsheet_id)
    ws = sh.worksheet(tab.tab_name)
    rows = ws.get_all_values()
    # Большинство реальных листов — 2 строки заголовка (раздел + названия
    # колонок), но не все (напр. "Цех" — только 1) — переопределяется через
    # column_mapping_json.header_rows при необходимости.
    header_rows = HEADER_ROWS
    if tab.format != WarehouseSheetTabFormat.movements and tab.column_mapping_json:
        header_rows = json.loads(tab.column_mapping_json).get("header_rows", HEADER_ROWS)
    start_row = max(tab.last_synced_row + 1, header_rows + 1)

    if tab.format == WarehouseSheetTabFormat.movements:
        outcome, last_row = _process_movements_format(db, connection.company_id, rows, start_row, dry_run)
        marker_col = MOVEMENTS_MARKER_COL
    else:
        outcome, last_row = _process_wide_format(db, connection.company_id, tab, rows, start_row, dry_run)
        marker_col = json.loads(tab.column_mapping_json or "{}").get("marker_col")

    if dry_run:
        return outcome.as_result(tab)

    db.commit()

    if marker_col and outcome.marks:
        cell_updates = [
            {"range": f"{marker_col}{row_number}", "values": [[value]]} for row_number, value in outcome.marks.items()
        ]
        ws.batch_update(cell_updates)
        # Маркер на wide-строке с несколькими калибрами — это склеенный список
        # ID движений через запятую (может быть 100+ символов), а колонка по
        # умолчанию наследует WRAP от соседей — без явного OVERFLOW_CELL это
        # раздувает высоту строки на глаз пользователя (реальный баг, найден
        # 2026-08-23). Overflow не портит данные — просто не переносит текст
        # визуально, сама ячейка остаётся читаемой по клику.
        ws.format(f"{marker_col}1:{marker_col}5000", {"wrapStrategy": "OVERFLOW_CELL"})

    tab.last_synced_row = last_row
    db.add(tab)
    db.commit()

    # Легаси wide-листы (Имп++ и т.п.) сами по себе не дают единого
    # непрерывного вида по всем видам сразу — дублируем каждое новое
    # движение в универсальный лист "Движения" тем же путём, что и движения,
    # созданные напрямую в приложении (см. push_movement_to_configured_tabs).
    # Не для самого формата movements — там это уже родной путь синка.
    if tab.format != WarehouseSheetTabFormat.movements and outcome.created_movements:
        try:
            for movement in outcome.created_movements:
                push_movement_to_configured_tabs(db, movement)
        except Exception:
            pass

    return outcome.as_result(tab)


def export_movement_to_sheet(db: Session, connection: WarehouseSheetConnection, tab: WarehouseSheetTab, movement) -> None:
    """Только для format == movements — дописывает движение, созданное в
    приложении, новой строкой в конец шаблонного листа. Легаси wide-формат
    листы на запись пока не поддержаны (см. план, фаза 2 — группировка
    нескольких движений в одну широкую строку требует отдельного движка)."""
    if tab.format != WarehouseSheetTabFormat.movements:
        return
    variant = db.get(ProductVariant, movement.product_variant_id)
    product = db.get(Product, variant.product_id) if variant else None
    warehouse = db.get(Warehouse, movement.warehouse_id)
    employee = db.get(Employee, movement.executor_id) if movement.executor_id else None
    label = MOVEMENTS_DIRECTION_LABELS.get(movement.direction)
    if not label:
        return  # production/transfer движения в универсальный шаблон не пишем — их нет смысла показывать полем

    gc = get_client(connection)
    ws = gc.open_by_key(tab.spreadsheet_id).worksheet(tab.tab_name)
    ws.append_row(
        [
            movement.date.isoformat(),
            warehouse.name if warehouse else "",
            product.name if product else "",
            variant.name if variant else "",
            label,
            float(movement.quantity),
            employee.full_name if employee else "",
            float(movement.payroll_rate) if movement.payroll_rate else "",
            movement.note or "",
            movement.id,
        ],
        value_input_option="USER_ENTERED",
    )


def push_movement_to_configured_tabs(db: Session, movement) -> None:
    """Вызывается из warehouse.py::create_movement (движение создано через
    само приложение) И из sync_tab() (движение только что импортировано из
    легаси wide-листа) — во втором случае это специально сделано, чтобы
    "Движения" стал единым непрерывным списком по всем видам сразу
    (см. 2026-08-23, месячный фильтр поверх всей таблицы). Цикл здесь не
    структурный запрет, а маркер: export_movement_to_sheet() сразу пишет
    movement.id в колонку-маркер добавленной строки, поэтому при следующем
    sync_tab() для самой "Движения" эта строка уже помечена и не
    импортируется повторно (см. _process_movements_format::already_marked).

    Ошибка Google API здесь не должна ронять создание самой операции —
    операция уже сохранена в БД, отправка в таблицу вторичный эффект."""
    connection = (
        db.query(WarehouseSheetConnection)
        .filter(
            WarehouseSheetConnection.company_id == movement.company_id,
            WarehouseSheetConnection.is_connected.is_(True),
        )
        .first()
    )
    if connection is None:
        return
    tabs = (
        db.query(WarehouseSheetTab)
        .filter(
            WarehouseSheetTab.connection_id == connection.id,
            WarehouseSheetTab.format == WarehouseSheetTabFormat.movements,
            WarehouseSheetTab.is_active.is_(True),
        )
        .all()
    )
    for tab in tabs:
        try:
            export_movement_to_sheet(db, connection, tab, movement)
        except Exception:
            pass


def export_balances(db: Session, connection: WarehouseSheetConnection, spreadsheet_id: str, company_id: str) -> None:
    gc = get_client(connection)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(BALANCES_TAB_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=BALANCES_TAB_NAME, rows=1000, cols=len(BALANCES_HEADER))

    balances = compute_balances(db, [company_id], include_empty=True)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    values = [BALANCES_HEADER] + [
        [b.warehouse_name, b.product_name, b.variant_name, b.quantity, b.reserved, b.available, now]
        for b in balances
    ]
    ws.clear()
    ws.update(values, "A1")
