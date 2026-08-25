"""order line unit price + transaction order_id

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-25

Связь Заказа с оплатой: OrderLine.unit_price_rub (опционально — старые
заказы без цены просто не участвуют в total_amount) + Transaction.order_id
(ручная привязка, не авто-создание при отгрузке — см. HANDOVER.md).
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_lines", sa.Column("unit_price_rub", sa.Numeric(14, 2), nullable=True))
    op.add_column("transactions", sa.Column("order_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key(
        "fk_transactions_order_id", "transactions", "orders", ["order_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_transactions_order_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "order_id")
    op.drop_column("order_lines", "unit_price_rub")
