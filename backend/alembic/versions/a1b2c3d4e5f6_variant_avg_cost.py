"""product variant avg cost + stock movement unit cost

Revision ID: a1b2c3d4e5f6
Revises: c9e4a71d5f83
Create Date: 2026-08-25

Себестоимость склада: ProductVariant.avg_cost_rub — средневзвешенная
себестоимость единицы, пересчитывается на каждом Приходе с указанной
unit_cost_rub (см. warehouse.py::build_movement()). Фундамент для
баланса (assets.inventory_rub) — количество на складе уже есть, стоимости
не было вообще.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "c9e4a71d5f83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_variants", sa.Column("avg_cost_rub", sa.Numeric(14, 2), nullable=True))
    op.add_column("stock_movements", sa.Column("unit_cost_rub", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_movements", "unit_cost_rub")
    op.drop_column("product_variants", "avg_cost_rub")
