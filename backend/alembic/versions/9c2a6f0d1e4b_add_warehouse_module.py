"""add warehouse module (склад-1)

Revision ID: 9c2a6f0d1e4b
Revises: 7a4c2e9f1b6d
Create Date: 2026-08-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9c2a6f0d1e4b'
down_revision = '7a4c2e9f1b6d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE roleenum ADD VALUE IF NOT EXISTS 'warehouse_operator'")

    op.create_table('warehouses',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('products',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_variants',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('product_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('stock_movements',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('warehouse_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('product_variant_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('direction', sa.Enum('in', 'out', 'production_consume', 'production_yield', 'transfer_in', 'transfer_out', 'adjustment', name='stockdirectionenum'), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('executor_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('payroll_rate', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('payroll_accrual_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('created_by', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['executor_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['payroll_accrual_id'], ['payroll_accruals.id'], ),
    sa.ForeignKeyConstraint(['product_variant_id'], ['product_variants.id'], ),
    sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('stock_movements')
    op.drop_table('product_variants')
    op.drop_table('products')
    op.drop_table('warehouses')
    sa.Enum(name='stockdirectionenum').drop(op.get_bind(), checkfirst=True)
    # Примечание: PostgreSQL не поддерживает удаление значения из enum (roleenum) —
    # откат добавленного 'warehouse_operator' невозможен без пересоздания типа.
