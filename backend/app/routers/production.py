from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import get_current_user, require_module, require_roles
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
from app.utils import delete_or_deactivate, get_or_404

router = APIRouter(prefix="/production", tags=["production"])

# Тот же контур ролей, что и для остального склада (см. warehouse.py/orders.py).
WAREHOUSE_EDITORS = [RoleEnum.admin, RoleEnum.warehouse_operator]

WAREHOUSE_MODULE = Depends(require_module("warehouse"))


def _validate_recipe_payload(db: Session, payload: ProductionRecipeIn, company_id: str) -> None:
    get_or_404(db, ProductVariant, payload.output_variant_id, "Вариант товара (выход) не найден", company_id=company_id)
    if not payload.inputs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нужен хотя бы один компонент сырья")
    for item in payload.inputs:
        get_or_404(db, ProductVariant, item.input_variant_id, "Вариант товара (сырьё) не найден", company_id=company_id)
        if item.qty_per_unit <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Норма расхода должна быть больше нуля")


@router.get("/recipes", response_model=list[ProductionRecipeOut], dependencies=[WAREHOUSE_MODULE])
def list_recipes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(ProductionRecipe).filter(ProductionRecipe.company_id == user.company_id).all()


@router.post(
    "/recipes",
    response_model=ProductionRecipeOut,
    dependencies=[Depends(require_roles(WAREHOUSE_EDITORS)), WAREHOUSE_MODULE],
)
def create_recipe(payload: ProductionRecipeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _validate_recipe_payload(db, payload, user.company_id)

    recipe = ProductionRecipe(
        company_id=user.company_id,
        name=payload.name,
        output_variant_id=payload.output_variant_id,
        is_active=payload.is_active,
    )
    recipe.inputs = [
        ProductionRecipeInput(company_id=user.company_id, input_variant_id=i.input_variant_id, qty_per_unit=i.qty_per_unit)
        for i in payload.inputs
    ]
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.patch(
    "/recipes/{recipe_id}",
    response_model=ProductionRecipeOut,
    dependencies=[Depends(require_roles(WAREHOUSE_EDITORS)), WAREHOUSE_MODULE],
)
def update_recipe(
    recipe_id: str, payload: ProductionRecipeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    recipe = get_or_404(db, ProductionRecipe, recipe_id, "Техкарта не найдена", company_id=user.company_id)
    _validate_recipe_payload(db, payload, user.company_id)

    recipe.name = payload.name
    recipe.output_variant_id = payload.output_variant_id
    recipe.is_active = payload.is_active
    recipe.inputs = [
        ProductionRecipeInput(company_id=user.company_id, input_variant_id=i.input_variant_id, qty_per_unit=i.qty_per_unit)
        for i in payload.inputs
    ]
    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete(
    "/recipes/{recipe_id}",
    dependencies=[Depends(require_roles(WAREHOUSE_EDITORS)), WAREHOUSE_MODULE],
)
def delete_recipe(recipe_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    recipe = get_or_404(db, ProductionRecipe, recipe_id, "Техкарта не найдена", company_id=user.company_id)
    deleted = delete_or_deactivate(db, recipe, [(ProductionRun, "recipe_id")])
    return {"deleted": deleted, "deactivated": not deleted}


@router.get("/runs", response_model=list[ProductionRunOut], dependencies=[WAREHOUSE_MODULE])
def list_runs(warehouse_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(ProductionRun).filter(ProductionRun.company_id == user.company_id)
    if warehouse_id:
        query = query.filter(ProductionRun.warehouse_id == warehouse_id)
    return query.order_by(ProductionRun.date.desc(), ProductionRun.created_at.desc()).all()


@router.post(
    "/runs",
    response_model=ProductionRunOut,
    dependencies=[Depends(require_roles(WAREHOUSE_EDITORS)), WAREHOUSE_MODULE],
)
def create_run(payload: ProductionRunIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    recipe = get_or_404(db, ProductionRecipe, payload.recipe_id, "Техкарта не найдена", company_id=user.company_id)
    get_or_404(db, Warehouse, payload.warehouse_id, "Склад не найден", company_id=user.company_id)
    if payload.output_qty <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Количество должно быть больше нуля")

    run = ProductionRun(
        company_id=user.company_id,
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
                company_id=user.company_id,
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
            company_id=user.company_id,
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


@router.delete(
    "/runs/{run_id}",
    dependencies=[Depends(require_roles(WAREHOUSE_EDITORS)), WAREHOUSE_MODULE],
)
def delete_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = get_or_404(db, ProductionRun, run_id, "Партия производства не найдена", company_id=user.company_id)
    db.query(StockMovement).filter(StockMovement.production_run_id == run.id).delete()
    db.delete(run)
    db.commit()
    log_action(db, user, action="delete", entity_type="production_run", entity_id=run_id)
    return {"deleted": True}
