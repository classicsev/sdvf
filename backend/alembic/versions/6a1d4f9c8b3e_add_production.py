"""add production (склад-3)

Revision ID: 6a1d4f9c8b3e
Revises: 3f7b8c2a5e1d
Create Date: 2026-08-06 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '6a1d4f9c8b3e'
down_revision = '3f7b8c2a5e1d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('production_recipes',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('output_variant_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['output_variant_id'], ['product_variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('production_recipe_inputs',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('recipe_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('input_variant_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('qty_per_unit', sa.Numeric(precision=12, scale=4), nullable=False),
    sa.ForeignKeyConstraint(['input_variant_id'], ['product_variants.id'], ),
    sa.ForeignKeyConstraint(['recipe_id'], ['production_recipes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('production_runs',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('recipe_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('warehouse_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('output_qty', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['recipe_id'], ['production_recipes.id'], ),
    sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('stock_movements', sa.Column('production_run_id', sa.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key(
        'fk_stock_movements_production_run_id', 'stock_movements', 'production_runs', ['production_run_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_stock_movements_production_run_id', 'stock_movements', type_='foreignkey')
    op.drop_column('stock_movements', 'production_run_id')
    op.drop_table('production_runs')
    op.drop_table('production_recipe_inputs')
    op.drop_table('production_recipes')
