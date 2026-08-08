"""add orders (склад-2)

Revision ID: 3f7b8c2a5e1d
Revises: 9c2a6f0d1e4b
Create Date: 2026-08-06 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '3f7b8c2a5e1d'
down_revision = '9c2a6f0d1e4b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('orders',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('counterparty_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('warehouse_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('status', sa.Enum('draft', 'reserved', 'shipped', 'cancelled', name='orderstatusenum'), nullable=False),
    sa.Column('requested_date', sa.Date(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['counterparty_id'], ['counterparties.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('order_lines',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('order_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('product_variant_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['product_variant_id'], ['product_variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('stock_movements', sa.Column('order_id', sa.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key('fk_stock_movements_order_id', 'stock_movements', 'orders', ['order_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_stock_movements_order_id', 'stock_movements', type_='foreignkey')
    op.drop_column('stock_movements', 'order_id')
    op.drop_table('order_lines')
    op.drop_table('orders')
    sa.Enum(name='orderstatusenum').drop(op.get_bind(), checkfirst=True)
