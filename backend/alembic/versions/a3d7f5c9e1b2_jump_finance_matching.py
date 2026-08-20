"""jump finance matching: counterparty defaults + transaction.jump_payment_id

Revision ID: a3d7f5c9e1b2
Revises: f2a7c4e91b36
Create Date: 2026-08-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a3d7f5c9e1b2'
down_revision = 'f2a7c4e91b36'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'counterparties', sa.Column('default_category_id', postgresql.UUID(as_uuid=False), nullable=True)
    )
    op.add_column(
        'counterparties', sa.Column('default_project_id', postgresql.UUID(as_uuid=False), nullable=True)
    )
    op.create_foreign_key(
        'fk_counterparties_default_category', 'counterparties', 'categories', ['default_category_id'], ['id']
    )
    op.create_foreign_key(
        'fk_counterparties_default_project', 'counterparties', 'projects', ['default_project_id'], ['id']
    )
    op.add_column('transactions', sa.Column('jump_payment_id', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'jump_payment_id')
    op.drop_constraint('fk_counterparties_default_project', 'counterparties', type_='foreignkey')
    op.drop_constraint('fk_counterparties_default_category', 'counterparties', type_='foreignkey')
    op.drop_column('counterparties', 'default_project_id')
    op.drop_column('counterparties', 'default_category_id')
