"""equipment (оборудование) — отдельный от товарного склада инвентарь

Revision ID: c3d7f92a5e18
Revises: 46e1df8abff8
Create Date: 2026-08-22

Лист "Склад" в реальной таблице пользователя — оборудование (насосы, шланги,
инструмент), не морепродукты. Не завязан на Product/ProductVariant/
StockMovement, простой инвентарный список с количеством per company.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3d7f92a5e18"
down_revision = "46e1df8abff8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=True),
        sa.Column("quantity_unit", sa.String(50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("equipment")
