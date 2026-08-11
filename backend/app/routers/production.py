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
from app.models import (
    ProductionRecipe,
    ProductionRecipeInput,
    ProductionRun,
    ProductVariant,
    RoleEnum,
    StockDirectionEnum,
    StockMovement,
    User,
    Warehouse,
)
from app.schemas import (
    ProductionRecipeIn,
    ProductionRecipeOut,
    ProductionRunIn,
    ProductionRunOut,
)
from app.utils import delete_or_deactivate, get_or_404_accessible

router = APIRouter(prefix="/production", tags=["production"])

# Тот же контур ролей, что и для остального склада (см. warehouse.py/orders.py).
WAREHOUSE_EDITORS = [RoleEnum.admin, RoleEnum.warehouse_operator]

WAREHOUSE_MODULE = Depends(require_module("warehouse"))


def _validate_recipe_payload(db: Session, payload: ProductionRecipeIn, accessible_ids: list[str], company_id: str) -> None:
    output_variant = get_or_404_accessible(
        db, ProductVariant, payload.output_variant_id, accessible_ids, "Вариант товара (выход) не найден"
    )
    if output_variant.company_id != company_id:
        raise HTTPException(status_code=400, detail="Вариант товара принадлежит другой компании")
    if not payload.inputs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужен хотя бы один компонент сырья")
    for item in payload.inputs:
        input_variant = get_or_404_accessible(
            db, ProductVariant, item.input_variant_id, accessible_ids, "Вариант товара (сырьё) не найден"
        )
        if input_variant.company_id != company_id:
            raise HTTPException(status_code=400, detail="Вариант товара принадлежит другой компании")
        if item.qty_per_unit <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Норма расхода должна быть больше нуля")


@router.get("/recipes", response_model=list[ProductionRecipeOut], dependencies=[WAREHOUSE_MODULE])
def list_recipes(
    company_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    company_ids = resolve_company_ids(db, user, company_id)
    return db.query(ProductionRecipe).filter(ProductionRecipe.company_id.in_(company_ids)).all()


@router.post("/recipes", response_model=ProductionRecipeOut, dependencies=[WAREHOUSE_MODULE])
def create_recipe(
    payload: ProductionRecipeIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, WAREHOUSE_EDITORS)
    _validate_recipe_payload(db, payload, get_accessible_company_ids(db, user), target)

    recipe = ProductionRecipe(
        company_id=target,
        name=payload.name,
        output_variant_id=payload.output_variant_id,
        is_active=payload.is_active,
    )
    recipe.inputs = [
        ProductionRecipeInput(company_id=target, input_variant_id=i.input_variant_id, qty_per_unit=i.qty_per_unit)
        for i in payload.inputs
    ]
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.patch("/recipes/{recipe_id}", response_model=ProductionRecipeOut, dependencies=[WAREHOUSE_MODULE])
def update_recipe(
    recipe_id: str, payload: ProductionRecipeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    accessible = get_accessible_company_ids(db, user)
    recipe = get_or_404_accessible(db, ProductionRecipe, recipe_id, accessible, "Техкарта не найдена")
    check_company_role(db, user, recipe.company_id, WAREHOUSE_EDITORS)
    _validate_recipe_payload(db, payload, accessible, recipe.company_id)

    recipe.name = payload.name
    recipe.output_variant_id = payload.output_variant_id
    recipe.is_active = payload.is_active
    recipe.inputs = [
        ProductionRecipeInput(
            company_id=recipe.company_id, input_variant_id=i.input_variant_id, qty_per_unit=i.qty_per_unit
        )
        for i in payload.inputs
    ]
    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/recipes/{recipe_id}", dependencies=[WAREHOUSE_MODULE])
def delete_recipe(recipe_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    recipe = get_or_404_accessible(
        db, ProductionRecipe, recipe_id, get_accessible_company_ids(db, user), "Техкарта не найдена"
    )
    check_company_role(db, user, recipe.company_id, WAREHOUSE_EDITORS)
    deleted = delete_or_deactivate(db, recipe, [(ProductionRun, "recipe_id")])
    return {"deleted": deleted, "deactivated": not deleted}


@router.get("/runs", response_model=list[ProductionRunOut], dependencies=[WAREHOUSE_MODULE])
def list_runs(
    warehouse_id: str | None = None,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    query = db.query(ProductionRun).filter(ProductionRun.company_id.in_(company_ids))
    if warehouse_id:
        query = query.filter(ProductionRun.warehouse_id == warehouse_id)
    return query.order_by(ProductionRun.date.desc(), ProductionRun.created_at.desc()).all()


@router.post("/runs", response_model=ProductionRunOut, dependencies=[WAREHOUSE_MODULE])
def create_run(payload: ProductionRunIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    accessible = get_accessible_company_ids(db, user)
    recipe = get_or_404_accessible(db, ProductionRecipe, payload.recipe_id, accessible, "Техкарта не найдена")
    check_company_role(db, user, recipe.company_id, WAREHOUSE_EDITORS)
    warehouse = get_or_404_accessible(db, Warehouse, payload.warehouse_id, accessible, "Склад не найден")
    if warehouse.company_id != recipe.company_id:
        raise HTTPException(status_code=400, detail="Склад принадлежит другой компании")
    if payload.output_qty <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество должно быть больше нуля")

    run = ProductionRun(
        company_id=recipe.company_id,
        recipe_id=recipe.id,
        warehouse_id=payload.warehouse_id,
        date=payload.date,
        output_qty=payload.output_qty,
        note=payload.note,
        created_by=user.id,
    )
    db.add(run)
    db.flush()

    for item in recipe.inputs:
        db.add(
            StockMovement(
                company_id=recipe.company_id,
                date=payload.date,
                warehouse_id=payload.warehouse_id,
                product_variant_id=item.input_variant_id,
                direction=StockDirectionEnum.production_consume,
                quantity=float(item.qty_per_unit) * payload.output_qty,
                note=f"Списано в производство: {recipe.name}",
                production_run_id=run.id,
                created_by=user.id,
            )
        )
    db.add(
        StockMovement(
            company_id=recipe.company_id,
            date=payload.date,
            warehouse_id=payload.warehouse_id,
            product_variant_id=recipe.output_variant_id,
            direction=StockDirectionEnum.production_yield,
            quantity=payload.output_qty,
            note=f"Получено с производства: {recipe.name}",
            production_run_id=run.id,
            created_by=user.id,
        )
    )
    db.commit()
    db.refresh(run)
    log_action(db, user, action="create", entity_type="production_run", entity_id=run.id)
    return run


@router.delete("/runs/{run_id}", dependencies=[WAREHOUSE_MODULE])
def delete_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = get_or_404_accessible(
        db, ProductionRun, run_id, get_accessible_company_ids(db, user), "Партия производства не найдена"
    )
    check_company_role(db, user, run.company_id, WAREHOUSE_EDITORS)
    db.query(StockMovement).filter(StockMovement.production_run_id == run.id).delete()
    db.delete(run)
    db.commit()
    log_action(db, user, action="delete", entity_type="production_run", entity_id=run_id)
    return {"deleted": True}
