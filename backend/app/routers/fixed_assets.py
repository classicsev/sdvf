from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import (
    check_company_role,
    get_accessible_company_ids,
    get_current_user,
    require_module,
    resolve_company_ids,
    resolve_write_company_id,
)
from app.database import get_db
from app.models import FixedAsset, RoleEnum, User
from app.schemas import FixedAssetIn, FixedAssetOut
from app.utils import get_or_404_accessible

router = APIRouter(prefix="/fixed-assets", tags=["fixed-assets"])

# Основные средства — та же строгость, что у бюджетов (см. reference.py) —
# только admin заводит/меняет амортизируемое имущество компании.
ADMIN_ONLY = [RoleEnum.admin]
FINANCE_MODULE = Depends(require_module("finance"))


def _book_value_rub(asset: FixedAsset, as_of: date) -> float:
    if asset.purchase_date > as_of:
        return float(asset.purchase_cost_rub)
    months_elapsed = (as_of.year - asset.purchase_date.year) * 12 + (as_of.month - asset.purchase_date.month)
    cost = Decimal(str(asset.purchase_cost_rub))
    monthly = cost / Decimal(asset.useful_life_months) if asset.useful_life_months else Decimal("0")
    book_value = cost - monthly * Decimal(max(months_elapsed, 0))
    return float(max(book_value, Decimal("0")))


def _to_out(asset: FixedAsset, as_of: date) -> FixedAssetOut:
    out = FixedAssetOut.model_validate(asset)
    out.book_value_rub = round(_book_value_rub(asset, as_of), 2)
    return out


@router.get("", response_model=list[FixedAssetOut], dependencies=[FINANCE_MODULE])
def list_fixed_assets(
    company_id: Optional[str] = None,
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_ids = resolve_company_ids(db, user, company_id)
    as_of = as_of or date.today()
    assets = db.query(FixedAsset).filter(FixedAsset.company_id.in_(company_ids)).order_by(FixedAsset.purchase_date).all()
    return [_to_out(a, as_of) for a in assets]


@router.post("", response_model=FixedAssetOut, dependencies=[FINANCE_MODULE])
def create_fixed_asset(
    payload: FixedAssetIn,
    company_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = resolve_write_company_id(db, user, company_id, ADMIN_ONLY)
    obj = FixedAsset(**payload.model_dump(), company_id=target)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _to_out(obj, date.today())


@router.patch("/{asset_id}", response_model=FixedAssetOut, dependencies=[FINANCE_MODULE])
def update_fixed_asset(
    asset_id: str, payload: FixedAssetIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    obj = get_or_404_accessible(db, FixedAsset, asset_id, get_accessible_company_ids(db, user), "Основное средство не найдено")
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return _to_out(obj, date.today())


@router.delete("/{asset_id}", dependencies=[FINANCE_MODULE])
def delete_fixed_asset(asset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = get_or_404_accessible(db, FixedAsset, asset_id, get_accessible_company_ids(db, user), "Основное средство не найдено")
    check_company_role(db, user, obj.company_id, ADMIN_ONLY)
    db.delete(obj)
    db.commit()
    return {"deleted": True}
