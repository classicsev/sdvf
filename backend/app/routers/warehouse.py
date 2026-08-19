import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, true
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
from app.models import (
    Employee,
    Order,
    OrderLine,
    OrderStatusEnum,
    PayrollAccrual,
    PayrollPayment,
    Product,
    ProductVariant,
    RoleEnum,
    StockDirectionEnum,
    StockMovement,
    User,
    Warehouse,
)
from app.schemas import (
    EmployeeMiniOut,
    MoveCompanyIn,
    ProductIn,
    ProductOut,
    ProductVariantIn,
    ProductVariantOut,
    StockBalanceOut,
    StockMovementIn,
    StockMovementOut,
    StockTransferIn,
    WarehouseIn,
    WarehouseOut,
)
from app.utils import delete_or_deactivate, get_or_404_accessible, move_to_company

router = APIRouter(prefix="/warehouse", tags=["warehouse"])

# Как и в модуле "Зарплата" (PAYROLL_EDITORS): один и тот же контур ролей управляет
# и справочниками домена (склады/товары/варианты), и операционными данными (движения) —
# складским сотрудникам не нужен админ на каждое новое наименование/калибр.
WAREHOUSE_EDITORS = [RoleEnum.admin, RoleEnum.warehouse_operator]
# Перенос между компаниями — только admin, как и у справочников
# (см. reference.py::_move_to_company) — более чувствительное действие.
ADMIN_ONLY = [RoleEnum.admin]

POSITIVE_DIRECTIONS = {StockDirectionEnum.in_, StockDirectionEnum.production_yield, StockDirectionEnum.transfer_in}
# Через общий эндпоинт создания движения нельзя завести производственные/трансферные
# записи напрямую — они создаются только парой через свои эндпоинты (перемещение —
# здесь же transfer, производство — отдельный роутер в Склад-3), чтобы гарантировать
# согласованность (расход сырья всегда идёт вместе с приходом готового и т.п.)
DIRECT_CREATE_DIRECTIONS = {StockDirectionEnum.in_, StockDirectionEnum.out, StockDirectionEnum.adjustment}

WAREHOUSE_MODULE = Depends(require_module("warehouse"))


def _signed_quantity_expr():
    return case(
        (StockMovement.direction == StockDirectionEnum.adjustment, StockMovement.quantity),
        (StockMovement.direction.in_(POSITIVE_DIRECTIONS), StockMovement.quantity),
        else_=-StockMovement.quantity,
    )


def _variant_sort_key(name: str) -> tuple:
    # Калибры вида "40/60", "300/500", "500+" должны идти по возрастанию числа, а не
    # по алфавиту строки (иначе "100/150" встаёт перед "40/60"). Варианты без числа в
    # начале имени (напр. "стандарт" для мактры) сортируются после калибров.
    match = re.match(r"(\d+)", name or "")
    if match:
        return (0, int(match.group(1)), name)
    return (1, 0, name)


def _apply_payroll_bridge(db: Session, movement: StockMovement, company_id: str) -> None:
    if movement.direction != StockDirectionEnum.in_ or not movement.executor_id or not movement.payroll_rate:
        return
    total = float(movement.quantity) * float(movement.payroll_rate)
    accrual = PayrollAccrual(
        company_id=company_id,
        employee_id=movement.executor_id,
        period=movement.date.replace(day=1),
        salary=total,
        bonus=0,
        deductions=0,
        total=total,
    )
    db.add(accrual)
    db.flush()
    movement.payroll_accrual_id = accrual.id


# ---------------------------------------------------------------------------
# Склады
# ---------------------------------------------------------------------------


@router.get("/warehouses", response_model=list[WarehouseOut], dependencies=[WAREHOUSE_MODULE])
def list_warehouses(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return db.query(Warehouse).filter(Warehouse.company_id.in_(company_ids)).all()


@router.post("/warehouses", response_model=WarehouseOut, dependencies=[WAREHOUSE_MODULE])
def create_warehouse(
    payload: WarehouseIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, WAREHOUSE_EDITORS)
    obj = Warehouse(**payload.model_dump(), company_id=target)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/warehouses/{warehouse_id}", response_model=WarehouseOut, dependencies=[WAREHOUSE_MODULE]
)
def update_warehouse(
    warehouse_id: str, payload: WarehouseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = get_or_404_accessible(db, Warehouse, warehouse_id, get_accessible_company_ids(db, user), "Склад не найден")
    check_company_role(db, user, obj.company_id, WAREHOUSE_EDITORS)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/warehouses/{warehouse_id}", dependencies=[WAREHOUSE_MODULE])
def delete_warehouse(warehouse_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = get_or_404_accessible(db, Warehouse, warehouse_id, get_accessible_company_ids(db, user), "Склад не найден")
    check_company_role(db, user, obj.company_id, WAREHOUSE_EDITORS)
    deleted = delete_or_deactivate(db, obj, [(StockMovement, "warehouse_id")])
    return {"deleted": deleted, "deactivated": not deleted}


@router.patch("/warehouses/{warehouse_id}/company", response_model=WarehouseOut, dependencies=[WAREHOUSE_MODULE])
def move_warehouse_company(
    warehouse_id: str, payload: MoveCompanyIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = get_or_404_accessible(db, Warehouse, warehouse_id, get_accessible_company_ids(db, user), "Склад не найден")
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    check_company_role(db, user, payload.company_id, ADMIN_ONLY)
    move_to_company(db, obj, payload.company_id, [(StockMovement, "warehouse_id")])
    db.refresh(obj)
    return obj


# ---------------------------------------------------------------------------
# Исполнители — только имя, без реквизитов/зарплатных данных. Отдельный эндпоинт,
# а не /payroll/employees: тот доступен лишь admin/payroll_operator и отдаёт
# расшифрованные банковские реквизиты, что складскому оператору видеть не нужно
# (ему нужен только список имён для поля "исполнитель" в приходе).
# ---------------------------------------------------------------------------


@router.get("/employees", response_model=list[EmployeeMiniOut], dependencies=[WAREHOUSE_MODULE])
def list_warehouse_employees(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return (
        db.query(Employee)
        .filter(Employee.company_id.in_(company_ids), Employee.status == "active")
        .all()
    )


# ---------------------------------------------------------------------------
# Товары
# ---------------------------------------------------------------------------


@router.get("/products", response_model=list[ProductOut], dependencies=[WAREHOUSE_MODULE])
def list_products(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return db.query(Product).filter(Product.company_id.in_(company_ids)).all()


@router.post("/products", response_model=ProductOut, dependencies=[WAREHOUSE_MODULE])
def create_product(
    payload: ProductIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, WAREHOUSE_EDITORS)
    obj = Product(**payload.model_dump(), company_id=target)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/products/{product_id}", response_model=ProductOut, dependencies=[WAREHOUSE_MODULE])
def update_product(
    product_id: str, payload: ProductIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = get_or_404_accessible(db, Product, product_id, get_accessible_company_ids(db, user), "Товар не найден")
    check_company_role(db, user, obj.company_id, WAREHOUSE_EDITORS)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/products/{product_id}", dependencies=[WAREHOUSE_MODULE])
def delete_product(product_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = get_or_404_accessible(db, Product, product_id, get_accessible_company_ids(db, user), "Товар не найден")
    check_company_role(db, user, obj.company_id, WAREHOUSE_EDITORS)
    deleted = delete_or_deactivate(db, obj, [(ProductVariant, "product_id")])
    return {"deleted": deleted, "deactivated": not deleted}


@router.patch("/products/{product_id}/company", response_model=ProductOut, dependencies=[WAREHOUSE_MODULE])
def move_product_company(
    product_id: str, payload: MoveCompanyIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = get_or_404_accessible(db, Product, product_id, get_accessible_company_ids(db, user), "Товар не найден")
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    check_company_role(db, user, payload.company_id, ADMIN_ONLY)
    move_to_company(db, obj, payload.company_id, [(ProductVariant, "product_id")])
    db.refresh(obj)
    return obj


# ---------------------------------------------------------------------------
# Варианты товара (калибры/модификации)
# ---------------------------------------------------------------------------


@router.get("/variants", response_model=list[ProductVariantOut], dependencies=[WAREHOUSE_MODULE])
def list_variants(
    product_id: str | None = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(ProductVariant).filter(ProductVariant.company_id.in_(company_ids))
    if product_id:
        query = query.filter(ProductVariant.product_id == product_id)
    return query.all()


@router.post("/variants", response_model=ProductVariantOut, dependencies=[WAREHOUSE_MODULE])
def create_variant(
    payload: ProductVariantIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    # Компания варианта определяется по товару — они всегда в одной компании.
    product = get_or_404_accessible(
        db, Product, payload.product_id, get_accessible_company_ids(db, user), "Товар не найден"
    )
    check_company_role(db, user, product.company_id, WAREHOUSE_EDITORS)
    obj = ProductVariant(**payload.model_dump(), company_id=product.company_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/variants/{variant_id}", response_model=ProductVariantOut, dependencies=[WAREHOUSE_MODULE])
def update_variant(
    variant_id: str, payload: ProductVariantIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    accessible = get_accessible_company_ids(db, user)
    obj = get_or_404_accessible(db, ProductVariant, variant_id, accessible, "Вариант не найден")
    check_company_role(db, user, obj.company_id, WAREHOUSE_EDITORS)
    product = get_or_404_accessible(db, Product, payload.product_id, accessible, "Товар не найден")
    if product.company_id != obj.company_id:
        raise HTTPException(status_code=400, detail="Товар принадлежит другой компании")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/variants/{variant_id}", dependencies=[WAREHOUSE_MODULE])
def delete_variant(variant_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = get_or_404_accessible(
        db, ProductVariant, variant_id, get_accessible_company_ids(db, user), "Вариант не найден"
    )
    check_company_role(db, user, obj.company_id, WAREHOUSE_EDITORS)
    deleted = delete_or_deactivate(db, obj, [(StockMovement, "product_variant_id")])
    return {"deleted": deleted, "deactivated": not deleted}


# ---------------------------------------------------------------------------
# Остатки
# ---------------------------------------------------------------------------


@router.get("/balances", response_model=list[StockBalanceOut], dependencies=[WAREHOUSE_MODULE])
def get_balances(
    warehouse_id: str | None = None,
    include_empty: bool = False,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    # Зарезервированное количество = сумма позиций заказов в статусе "reserved" по тому
    # же складу и варианту — доступно-к-обещанию (available) не хранится, а считается
    # так же на лету, как и сам остаток.
    reserved_subq = (
        db.query(
            Order.warehouse_id.label("warehouse_id"),
            OrderLine.product_variant_id.label("product_variant_id"),
            func.sum(OrderLine.quantity).label("reserved_qty"),
        )
        .join(OrderLine, OrderLine.order_id == Order.id)
        .filter(Order.status == OrderStatusEnum.reserved, Order.company_id.in_(company_ids))
        .group_by(Order.warehouse_id, OrderLine.product_variant_id)
        .subquery()
    )
    movement_subq = (
        db.query(
            StockMovement.warehouse_id.label("warehouse_id"),
            StockMovement.product_variant_id.label("product_variant_id"),
            func.sum(_signed_quantity_expr()).label("quantity"),
        )
        .filter(StockMovement.company_id.in_(company_ids))
        .group_by(StockMovement.warehouse_id, StockMovement.product_variant_id)
        .subquery()
    )

    if include_empty:
        # Показать все активные варианты товаров на всех активных складах, даже те,
        # по которым ещё не было ни одного движения (остаток 0) — а не только те,
        # что уже засветились в ленте движений.
        query = (
            db.query(
                Warehouse.company_id,
                Warehouse.id.label("warehouse_id"),
                Warehouse.name.label("warehouse_name"),
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.unit,
                ProductVariant.id.label("product_variant_id"),
                ProductVariant.name.label("variant_name"),
                func.coalesce(movement_subq.c.quantity, 0).label("quantity"),
                reserved_subq.c.reserved_qty,
            )
            .select_from(Warehouse)
            .join(ProductVariant, ProductVariant.company_id == Warehouse.company_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .outerjoin(
                movement_subq,
                (movement_subq.c.warehouse_id == Warehouse.id)
                & (movement_subq.c.product_variant_id == ProductVariant.id),
            )
            .outerjoin(
                reserved_subq,
                (reserved_subq.c.warehouse_id == Warehouse.id)
                & (reserved_subq.c.product_variant_id == ProductVariant.id),
            )
            .filter(
                Warehouse.company_id.in_(company_ids),
                Warehouse.is_active.is_(True),
                ProductVariant.is_active.is_(True),
                Product.is_active.is_(True),
            )
        )
        if warehouse_id:
            query = query.filter(Warehouse.id == warehouse_id)
    else:
        query = (
            db.query(
                Warehouse.company_id,
                movement_subq.c.warehouse_id,
                Warehouse.name.label("warehouse_name"),
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.unit,
                ProductVariant.id.label("product_variant_id"),
                ProductVariant.name.label("variant_name"),
                movement_subq.c.quantity,
                reserved_subq.c.reserved_qty,
            )
            .select_from(movement_subq)
            .join(Warehouse, Warehouse.id == movement_subq.c.warehouse_id)
            .join(ProductVariant, ProductVariant.id == movement_subq.c.product_variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .outerjoin(
                reserved_subq,
                (reserved_subq.c.warehouse_id == movement_subq.c.warehouse_id)
                & (reserved_subq.c.product_variant_id == movement_subq.c.product_variant_id),
            )
        )
        if warehouse_id:
            query = query.filter(movement_subq.c.warehouse_id == warehouse_id)

    results = []
    for row in query.all():
        quantity = float(row.quantity or 0)
        reserved = float(row.reserved_qty or 0)
        results.append(
            StockBalanceOut(
                company_id=row.company_id,
                warehouse_id=row.warehouse_id,
                warehouse_name=row.warehouse_name,
                product_id=row.product_id,
                product_name=row.product_name,
                unit=row.unit,
                product_variant_id=row.product_variant_id,
                variant_name=row.variant_name,
                quantity=quantity,
                reserved=reserved,
                available=quantity - reserved,
            )
        )

    results.sort(key=lambda b: (b.warehouse_name, b.product_name, _variant_sort_key(b.variant_name)))
    return results


# ---------------------------------------------------------------------------
# Движения
# ---------------------------------------------------------------------------


@router.get("/movements", response_model=list[StockMovementOut], dependencies=[WAREHOUSE_MODULE])
def list_movements(
    warehouse_id: str | None = None,
    product_variant_id: str | None = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(StockMovement).filter(StockMovement.company_id.in_(company_ids))
    if warehouse_id:
        query = query.filter(StockMovement.warehouse_id == warehouse_id)
    if product_variant_id:
        query = query.filter(StockMovement.product_variant_id == product_variant_id)
    return query.order_by(StockMovement.date.desc(), StockMovement.created_at.desc()).all()


@router.post("/movements", response_model=StockMovementOut, dependencies=[WAREHOUSE_MODULE])
def create_movement(
    payload: StockMovementIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.direction not in DIRECT_CREATE_DIRECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Это направление движения создаётся только через отдельный эндпоинт (перемещение/производство)",
        )
    if payload.direction != StockDirectionEnum.adjustment and payload.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество должно быть больше нуля")

    # Компания движения определяется по складу — все ссылки (вариант, сотрудник)
    # должны принадлежать той же компании.
    accessible = get_accessible_company_ids(db, user)
    warehouse = get_or_404_accessible(db, Warehouse, payload.warehouse_id, accessible, "Склад не найден")
    check_company_role(db, user, warehouse.company_id, WAREHOUSE_EDITORS)
    variant = get_or_404_accessible(
        db, ProductVariant, payload.product_variant_id, accessible, "Вариант товара не найден"
    )
    if variant.company_id != warehouse.company_id:
        raise HTTPException(status_code=400, detail="Вариант товара принадлежит другой компании")
    if payload.executor_id:
        employee = get_or_404_accessible(db, Employee, payload.executor_id, accessible, "Сотрудник не найден")
        if employee.company_id != warehouse.company_id:
            raise HTTPException(status_code=400, detail="Сотрудник принадлежит другой компании")

    movement = StockMovement(
        company_id=warehouse.company_id,
        date=payload.date,
        warehouse_id=payload.warehouse_id,
        product_variant_id=payload.product_variant_id,
        direction=payload.direction,
        quantity=payload.quantity,
        note=payload.note,
        executor_id=payload.executor_id,
        payroll_rate=payload.payroll_rate,
        created_by=user.id,
    )
    db.add(movement)
    db.flush()

    _apply_payroll_bridge(db, movement, warehouse.company_id)

    db.commit()
    db.refresh(movement)
    log_action(db, user, action="create", entity_type="stock_movement", entity_id=movement.id, company_id=warehouse.company_id)
    return movement


@router.delete("/movements/{movement_id}", dependencies=[WAREHOUSE_MODULE])
def delete_movement(movement_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    movement = get_or_404_accessible(
        db, StockMovement, movement_id, get_accessible_company_ids(db, user), "Движение не найдено"
    )
    check_company_role(db, user, movement.company_id, WAREHOUSE_EDITORS)

    accrual = None
    if movement.payroll_accrual_id:
        if db.query(PayrollPayment).filter(PayrollPayment.accrual_id == movement.payroll_accrual_id).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="По связанному начислению зарплаты уже есть выплата — сначала отмените её",
            )
        accrual = db.get(PayrollAccrual, movement.payroll_accrual_id)

    db.delete(movement)
    # Флашим раньше accrual-delete: без явного relationship() между StockMovement и
    # PayrollAccrual SQLAlchemy не гарантирует порядок двух independent delete() в одном
    # flush, а удалять accrual, пока на него ещё ссылается movement.payroll_accrual_id,
    # нельзя (FK).
    db.flush()
    if accrual:
        db.delete(accrual)
    db.commit()
    log_action(db, user, action="delete", entity_type="stock_movement", entity_id=movement_id, company_id=movement.company_id)
    return {"deleted": True}


@router.post("/movements/transfer", response_model=list[StockMovementOut], dependencies=[WAREHOUSE_MODULE])
def transfer_stock(payload: StockTransferIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.from_warehouse_id == payload.to_warehouse_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Склад отправления и назначения совпадают")
    if payload.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество должно быть больше нуля")

    accessible = get_accessible_company_ids(db, user)
    from_wh = get_or_404_accessible(db, Warehouse, payload.from_warehouse_id, accessible, "Склад отправления не найден")
    check_company_role(db, user, from_wh.company_id, WAREHOUSE_EDITORS)
    to_wh = get_or_404_accessible(db, Warehouse, payload.to_warehouse_id, accessible, "Склад назначения не найден")
    if to_wh.company_id != from_wh.company_id:
        raise HTTPException(status_code=400, detail="Перемещение возможно только между складами одной компании")
    variant = get_or_404_accessible(
        db, ProductVariant, payload.product_variant_id, accessible, "Вариант товара не найден"
    )
    if variant.company_id != from_wh.company_id:
        raise HTTPException(status_code=400, detail="Вариант товара принадлежит другой компании")

    out_movement = StockMovement(
        company_id=from_wh.company_id,
        date=payload.date,
        warehouse_id=payload.from_warehouse_id,
        product_variant_id=payload.product_variant_id,
        direction=StockDirectionEnum.transfer_out,
        quantity=payload.quantity,
        note=payload.note,
        created_by=user.id,
    )
    in_movement = StockMovement(
        company_id=from_wh.company_id,
        date=payload.date,
        warehouse_id=payload.to_warehouse_id,
        product_variant_id=payload.product_variant_id,
        direction=StockDirectionEnum.transfer_in,
        quantity=payload.quantity,
        note=payload.note,
        created_by=user.id,
    )
    db.add_all([out_movement, in_movement])
    db.commit()
    db.refresh(out_movement)
    db.refresh(in_movement)
    log_action(
        db,
        user,
        action="transfer",
        entity_type="stock_movement",
        entity_id=out_movement.id,
        details={"to_movement_id": in_movement.id, "quantity": payload.quantity},
        company_id=from_wh.company_id,
    )
    return [out_movement, in_movement]
