from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids,
)
from app.config import settings
from app.database import get_db
from app.integrations.sdvf import SdvfClient, SdvfError
from app.models import (
    Company,
    Counterparty,
    Order,
    OrderLine,
    OrderStatusEnum,
    ProductVariant,
    RoleEnum,
    StockDirectionEnum,
    StockMovement,
    Transaction,
    User,
    Warehouse,
)
from app.schemas import OrderCreateIn, OrderLineIn, OrderOut, OrderUpdateIn, SdvfDocumentRefOut, SdvfGenerateDocumentIn
from app.utils import get_or_404_accessible

router = APIRouter(prefix="/orders", tags=["orders"])

# Тот же контур ролей, что и для остального склада (см. warehouse.py) — заказы
# и резервирование управляются теми же людьми, что и сами движения товара.
WAREHOUSE_EDITORS = [RoleEnum.admin, RoleEnum.warehouse_operator]

OPEN_STATUSES = (OrderStatusEnum.draft, OrderStatusEnum.reserved)

WAREHOUSE_MODULE = Depends(require_module("warehouse"))


def _get_order_or_404(db: Session, user: User, order_id: str) -> Order:
    return get_or_404_accessible(db, Order, order_id, get_accessible_company_ids(db, user), "Заказ не найден")


# Связь Заказа с оплатой (см. HANDOVER.md) — total/paid/balance_due не
# хранятся, проставляются как обычные Python-атрибуты на уже загруженные
# ORM-объекты прямо перед сериализацией (OrderOut читает их через
# from_attributes=True). Один bulk-запрос по Transaction на весь список —
# не N+1 на каждый заказ.
def _attach_payment_fields(db: Session, orders):
    single = isinstance(orders, Order)
    order_list = [orders] if single else list(orders)
    if order_list:
        ids = [o.id for o in order_list]
        paid_rows = (
            db.query(Transaction.order_id, func.sum(Transaction.amount_rub))
            .filter(Transaction.order_id.in_(ids), Transaction.payment_confirmed.is_(True))
            .group_by(Transaction.order_id)
            .all()
        )
        paid_by_order = {row[0]: float(row[1]) for row in paid_rows}
        for o in order_list:
            has_prices = any(l.unit_price_rub is not None for l in o.lines)
            paid = round(paid_by_order.get(o.id, 0.0), 2)
            o.paid_amount_rub = paid
            if has_prices:
                total = round(sum(float(l.quantity) * float(l.unit_price_rub or 0) for l in o.lines), 2)
                o.total_amount_rub = total
                o.balance_due_rub = round(total - paid, 2)
            else:
                o.total_amount_rub = None
                o.balance_due_rub = None
    return orders


@router.get("", response_model=list[OrderOut], dependencies=[WAREHOUSE_MODULE])
def list_orders(
    status_filter: str | None = None,
    warehouse_id: str | None = None,
    counterparty_id: str | None = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(Order).filter(Order.company_id.in_(company_ids))
    if status_filter:
        query = query.filter(Order.status == status_filter)
    if warehouse_id:
        query = query.filter(Order.warehouse_id == warehouse_id)
    if counterparty_id:
        query = query.filter(Order.counterparty_id == counterparty_id)
    return _attach_payment_fields(db, query.order_by(Order.created_at.desc()).all())


@router.post("", response_model=OrderOut, dependencies=[WAREHOUSE_MODULE])
def create_order(payload: OrderCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Компания заказа определяется по складу — контрагент и товары должны
    # принадлежать той же компании.
    accessible = get_accessible_company_ids(db, user)
    warehouse = get_or_404_accessible(db, Warehouse, payload.warehouse_id, accessible, "Склад не найден")
    check_company_role(db, user, warehouse.company_id, WAREHOUSE_EDITORS)
    counterparty = get_or_404_accessible(db, Counterparty, payload.counterparty_id, accessible, "Контрагент не найден")
    if counterparty.company_id != warehouse.company_id:
        raise HTTPException(status_code=400, detail="Контрагент принадлежит другой компании")
    if not payload.lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужна хотя бы одна позиция")
    for line in payload.lines:
        variant = get_or_404_accessible(
            db, ProductVariant, line.product_variant_id, accessible, "Вариант товара не найден"
        )
        if variant.company_id != warehouse.company_id:
            raise HTTPException(status_code=400, detail="Вариант товара принадлежит другой компании")
        if line.quantity <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество должно быть больше нуля")

    order = Order(
        company_id=warehouse.company_id,
        counterparty_id=payload.counterparty_id,
        warehouse_id=payload.warehouse_id,
        status=OrderStatusEnum.draft,
        requested_date=payload.requested_date,
        courier=payload.courier,
        note=payload.note,
        incoterms=payload.incoterms,
        incoterms_place=payload.incoterms_place,
        payment_terms=payload.payment_terms,
        created_by=user.id,
    )
    order.lines = [
        OrderLine(
            company_id=warehouse.company_id,
            product_variant_id=l.product_variant_id,
            quantity=l.quantity,
            unit_price_rub=l.unit_price_rub,
            package_count=l.package_count,
            package_type=l.package_type,
            gross_weight=l.gross_weight,
            net_weight=l.net_weight,
            marks=l.marks,
        )
        for l in payload.lines
    ]
    db.add(order)
    db.commit()
    db.refresh(order)
    log_action(db, user, action="create", entity_type="order", entity_id=order.id, company_id=warehouse.company_id)
    return _attach_payment_fields(db, order)


@router.patch("/{order_id}", response_model=OrderOut, dependencies=[WAREHOUSE_MODULE])
def update_order(
    order_id: str, payload: OrderUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    if order.status not in OPEN_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заказ закрыт, изменения недоступны")
    accessible = get_accessible_company_ids(db, user)
    changes = payload.model_dump(exclude_unset=True, exclude={"lines"})
    if changes.get("warehouse_id"):
        warehouse = get_or_404_accessible(db, Warehouse, changes["warehouse_id"], accessible, "Склад не найден")
        if warehouse.company_id != order.company_id:
            raise HTTPException(status_code=400, detail="Склад принадлежит другой компании")
    if changes.get("counterparty_id"):
        counterparty = get_or_404_accessible(
            db, Counterparty, changes["counterparty_id"], accessible, "Контрагент не найден"
        )
        if counterparty.company_id != order.company_id:
            raise HTTPException(status_code=400, detail="Контрагент принадлежит другой компании")
    for k, v in changes.items():
        setattr(order, k, v)

    if payload.lines is not None:
        if not payload.lines:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужна хотя бы одна позиция")
        for line in payload.lines:
            variant = get_or_404_accessible(
                db, ProductVariant, line.product_variant_id, accessible, "Вариант товара не найден"
            )
            if variant.company_id != order.company_id:
                raise HTTPException(status_code=400, detail="Вариант товара принадлежит другой компании")
            if line.quantity <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество должно быть больше нуля")
        for old_line in list(order.lines):
            db.delete(old_line)
        db.flush()
        order.lines = [
            OrderLine(
                company_id=order.company_id,
                product_variant_id=l.product_variant_id,
                quantity=l.quantity,
                unit_price_rub=l.unit_price_rub,
                package_count=l.package_count,
                package_type=l.package_type,
                gross_weight=l.gross_weight,
                net_weight=l.net_weight,
                marks=l.marks,
            )
            for l in payload.lines
        ]

    db.commit()
    db.refresh(order)
    log_action(db, user, action="update", entity_type="order", entity_id=order.id, company_id=order.company_id)
    return _attach_payment_fields(db, order)


@router.delete("/{order_id}", dependencies=[WAREHOUSE_MODULE])
def delete_order(order_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    if order.status != OrderStatusEnum.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Удалить можно только черновик — остальные отменяйте"
        )
    db.delete(order)
    db.commit()
    return {"deleted": True}


@router.post("/{order_id}/lines", response_model=OrderOut, dependencies=[WAREHOUSE_MODULE])
def add_order_line(
    order_id: str, payload: OrderLineIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    if order.status != OrderStatusEnum.draft:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Менять состав можно только в черновике")
    variant = get_or_404_accessible(
        db, ProductVariant, payload.product_variant_id, get_accessible_company_ids(db, user), "Вариант товара не найден"
    )
    if variant.company_id != order.company_id:
        raise HTTPException(status_code=400, detail="Вариант товара принадлежит другой компании")
    if payload.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество должно быть больше нуля")

    db.add(
        OrderLine(
            company_id=order.company_id,
            order_id=order.id,
            product_variant_id=payload.product_variant_id,
            quantity=payload.quantity,
            unit_price_rub=payload.unit_price_rub,
        )
    )
    db.commit()
    db.refresh(order)
    return _attach_payment_fields(db, order)


@router.delete("/{order_id}/lines/{line_id}", response_model=OrderOut, dependencies=[WAREHOUSE_MODULE])
def remove_order_line(
    order_id: str, line_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    if order.status != OrderStatusEnum.draft:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Менять состав можно только в черновике")
    line = get_or_404_accessible(db, OrderLine, line_id, get_accessible_company_ids(db, user), "Позиция не найдена")
    if line.order_id != order.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Позиция не найдена")

    db.delete(line)
    db.commit()
    db.refresh(order)
    return _attach_payment_fields(db, order)


def _transition(db: Session, order: Order, allowed: tuple, new_status: OrderStatusEnum, user: User) -> Order:
    if order.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Нельзя перевести заказ из статуса «{order.status.value}» в «{new_status.value}»",
        )
    order.status = new_status
    db.commit()
    db.refresh(order)
    log_action(db, user, action=f"order_{new_status.value}", entity_type="order", entity_id=order.id, company_id=order.company_id)
    return _attach_payment_fields(db, order)


@router.post("/{order_id}/reserve", response_model=OrderOut, dependencies=[WAREHOUSE_MODULE])
def reserve_order(order_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    return _transition(db, order, (OrderStatusEnum.draft,), OrderStatusEnum.reserved, user)


@router.post("/{order_id}/unreserve", response_model=OrderOut, dependencies=[WAREHOUSE_MODULE])
def unreserve_order(order_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    return _transition(db, order, (OrderStatusEnum.reserved,), OrderStatusEnum.draft, user)


@router.post("/{order_id}/cancel", response_model=OrderOut, dependencies=[WAREHOUSE_MODULE])
def cancel_order(order_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    return _transition(db, order, OPEN_STATUSES, OrderStatusEnum.cancelled, user)


@router.post("/{order_id}/ship", response_model=OrderOut, dependencies=[WAREHOUSE_MODULE])
def ship_order(order_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    if order.status not in OPEN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Нельзя отгрузить заказ из статуса «{order.status.value}»"
        )

    today = datetime.utcnow().date()
    shipped_movements = []
    for line in order.lines:
        movement = StockMovement(
            company_id=order.company_id,
            date=today,
            warehouse_id=order.warehouse_id,
            product_variant_id=line.product_variant_id,
            direction=StockDirectionEnum.out,
            quantity=line.quantity,
            note="Отгрузка по заказу",
            order_id=order.id,
            created_by=user.id,
        )
        db.add(movement)
        shipped_movements.append(movement)
    order.status = OrderStatusEnum.shipped
    db.commit()
    db.refresh(order)
    log_action(db, user, action="order_shipped", entity_type="order", entity_id=order.id, company_id=order.company_id)

    # Как и при создании движения напрямую (warehouse.py::create_movement) —
    # отгрузка заказа тоже должна попасть в подключённые Google-таблицы;
    # раньше этого не было (StockMovement создавался в обход build_movement),
    # найдено по жалобе пользователя, что заказ не появился в таблице.
    try:
        from app.warehouse_sheets import push_movement_to_configured_tabs

        for movement in shipped_movements:
            push_movement_to_configured_tabs(db, movement)
    except Exception:
        pass

    return _attach_payment_fields(db, order)


# ---------------------------------------------------------------------------
# Интеграция с СДВФ — генерация Счёт/УПД по заказу
# ---------------------------------------------------------------------------


def _sdvf_client() -> SdvfClient:
    if not settings.sdvf_base_url or not settings.sdvf_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Интеграция с СДВФ не настроена"
        )
    return SdvfClient(settings.sdvf_base_url, settings.sdvf_api_key)


def _validate_sdvf_org_details(company) -> None:
    if not company.sdvf_org_naming or not company.sdvf_org_inn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Заполните реквизиты организации для СДВФ в настройках компании (Модули)",
        )


def _validate_counterparty_inn(counterparty: Counterparty) -> None:
    if not counterparty.inn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У контрагента не указан ИНН — обязателен для документов СДВФ",
        )


def _resolve_sdvf_organization(client: SdvfClient, company) -> int:
    """Валидация (наличие реквизитов) — отдельно в _validate_sdvf_org_details,
    вызывается раньше в эндпоинте, до всех сетевых вызовов. Здесь только сеть."""
    try:
        org = client.get_or_create_organization(
            inn=company.sdvf_org_inn,
            naming=company.sdvf_org_naming,
            kpp=company.sdvf_org_kpp,
            ogrn=company.sdvf_org_ogrn,
            address=company.sdvf_org_address,
            phone=company.sdvf_org_phone,
        )
    except SdvfError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return org["id"]


def _resolve_sdvf_counterparty(client: SdvfClient, counterparty: Counterparty, company) -> int:
    """Карточка контрагента в СДВФ. organization_inn — чтобы она появилась в
    аккаунте клиента (владельца организации), а не у служебного пользователя."""
    try:
        buyer = client.get_or_create_counterparty(
            inn=counterparty.inn,
            naming=counterparty.name,
            kpp=counterparty.kpp,
            ogrn=counterparty.ogrn,
            address=counterparty.address,
            phone=counterparty.phone,
            organization_inn=company.sdvf_org_inn,
        )
    except SdvfError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return buyer["id"]


def _build_sdvf_lines(db: Session, order: Order, payload: SdvfGenerateDocumentIn) -> list[dict]:
    order_line_ids = {line.id for line in order.lines}
    payload_line_ids = {line.order_line_id for line in payload.lines}
    if order_line_ids != payload_line_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужна цена ровно для каждой позиции заказа, не больше и не меньше",
        )

    lines_by_id = {line.id: line for line in order.lines}
    variant_ids = [line.product_variant_id for line in order.lines]
    variants_by_id = {v.id: v for v in db.query(ProductVariant).filter(ProductVariant.id.in_(variant_ids))}

    result = []
    for price_line in payload.lines:
        order_line = lines_by_id[price_line.order_line_id]
        variant = variants_by_id[order_line.product_variant_id]
        name = f"{variant.product.name} {variant.name}".strip()
        amount = round(float(order_line.quantity) * price_line.price, 2)
        result.append(
            {
                "name": name,
                "unit_of_measurement": variant.product.unit,
                "quantity": order_line.quantity,
                "price": price_line.price,
                "amount": amount,
                "nds_product": price_line.nds_product,
            }
        )
    return result


@router.post("/{order_id}/generate-invoice", response_model=SdvfDocumentRefOut, dependencies=[WAREHOUSE_MODULE])
def generate_invoice(
    order_id: str,
    payload: SdvfGenerateDocumentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    company = db.get(Company, order.company_id)
    counterparty = get_or_404_accessible(
        db, Counterparty, order.counterparty_id, get_accessible_company_ids(db, user), "Контрагент не найден"
    )

    # Порядок важен: сначала проверяем, что интеграция вообще настроена (503),
    # затем всю локальную валидацию (400) — состав строк, реквизиты, ИНН —
    # и только потом идём в сеть к СДВФ (502 при сбое там).
    client = _sdvf_client()
    lines = _build_sdvf_lines(db, order, payload)
    _validate_sdvf_org_details(company)
    _validate_counterparty_inn(counterparty)

    counterparty_id = _resolve_sdvf_counterparty(client, counterparty, company)
    organization_id = _resolve_sdvf_organization(client, company)

    try:
        result = client.create_invoice(
            organization_id=organization_id,
            counterparty_id=counterparty_id,
            name=order.id[:8],
            doc_date=datetime.utcnow().date(),
            lines=lines,
            nds=payload.nds,
            nds_type=payload.nds_type,
        )
    except SdvfError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    order.sdvf_invoice_ref = result
    db.commit()
    log_action(db, user, action="order_generate_invoice", entity_type="order", entity_id=order.id, company_id=order.company_id)
    return result


@router.post("/{order_id}/generate-utd", response_model=SdvfDocumentRefOut, dependencies=[WAREHOUSE_MODULE])
def generate_utd(
    order_id: str,
    payload: SdvfGenerateDocumentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = _get_order_or_404(db, user, order_id)
    check_company_role(db, user, order.company_id, WAREHOUSE_EDITORS)
    company = db.get(Company, order.company_id)
    counterparty = get_or_404_accessible(
        db, Counterparty, order.counterparty_id, get_accessible_company_ids(db, user), "Контрагент не найден"
    )

    # Порядок важен: сначала проверяем, что интеграция вообще настроена (503),
    # затем всю локальную валидацию (400) — состав строк, реквизиты, ИНН —
    # и только потом идём в сеть к СДВФ (502 при сбое там).
    client = _sdvf_client()
    lines = _build_sdvf_lines(db, order, payload)
    _validate_sdvf_org_details(company)
    _validate_counterparty_inn(counterparty)

    counterparty_id = _resolve_sdvf_counterparty(client, counterparty, company)
    organization_id = _resolve_sdvf_organization(client, company)

    try:
        result = client.create_utd(
            organization_id=organization_id,
            counterparty_id=counterparty_id,
            name=order.id[:8],
            doc_date=datetime.utcnow().date(),
            lines=lines,
            nds=payload.nds,
            nds_type=payload.nds_type,
            shipment_date=datetime.utcnow().date() if order.status == OrderStatusEnum.shipped else None,
        )
    except SdvfError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    order.sdvf_utd_ref = result
    db.commit()
    log_action(db, user, action="order_generate_utd", entity_type="order", entity_id=order.id, company_id=order.company_id)
    return result


@router.get("/{order_id}/sdvf-pdf", dependencies=[WAREHOUSE_MODULE])
def sdvf_pdf(
    order_id: str,
    doc: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Проксирует PDF от СДВФ через бэкенд — прямая ссылка на pdf_url СДВФ
    требует X-API-Key, которого у браузера нет и быть не должно (секрет
    интеграции не должен попадать на фронтенд). Доступ проверяется обычной
    авторизацией Учёта (компания/модуль), а не отдельным токеном в URL."""
    if doc not in ("invoice", "utd"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный тип документа")

    order = _get_order_or_404(db, user, order_id)
    ref = order.sdvf_invoice_ref if doc == "invoice" else order.sdvf_utd_ref
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ ещё не сформирован")
    if not settings.sdvf_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Интеграция с СДВФ не настроена")

    try:
        # follow_redirects — pdf_url от СДВФ иногда приходит со схемой http:// (Django
        # за nginx строит абсолютный URL без учёта реального https снаружи), а их nginx
        # сам редиректит http→https; httpx по умолчанию редиректы не проходит.
        resp = httpx.get(
            ref["pdf_url"], headers={"X-API-Key": settings.sdvf_api_key}, timeout=30.0, follow_redirects=True
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Ошибка соединения с СДВФ: {exc}")
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="СДВФ вернул ошибку при получении PDF")

    return Response(content=resp.content, media_type="application/pdf")
