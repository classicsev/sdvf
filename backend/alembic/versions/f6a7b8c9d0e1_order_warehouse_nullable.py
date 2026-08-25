"""make order warehouse_id nullable, order_line product_variant_id nullable + description

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-25

Заказ → опциональный склад ("сделка без товара") — склад сейчас опциональный
модуль компании (module_warehouse_enabled), не обязан существовать для всех
клиентов. Позволяет завести заказ на чистую услугу: строка без
product_variant_id, вместо неё свободный текст description.
"""

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("orders", "warehouse_id", nullable=True)
    op.alter_column("order_lines", "product_variant_id", nullable=True)
    op.add_column("order_lines", sa.Column("description", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("order_lines", "description")
    op.alter_column("order_lines", "product_variant_id", nullable=False)
    op.alter_column("orders", "warehouse_id", nullable=False)
