"""add companies table (мультитенантность)

Revision ID: 8d4f1a6c2b9e
Revises: 6a1d4f9c8b3e
Create Date: 2026-08-07 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '8d4f1a6c2b9e'
down_revision = '6a1d4f9c8b3e'
branch_labels = None
depends_on = None

# Компания №1 — реальный бизнес пользователя, к которому в следующей миграции
# привязываются все уже существующие данные. Захардкожен как константа (не
# gen_random_uuid() внутри upgrade()) — id должен быть одинаковым при каждом
# прогоне миграции, а не случайным.
COMPANY_1_ID = '2c7cc73f-9bc7-431f-9084-277a65d1ece8'


def upgrade() -> None:
    op.create_table('companies',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('module_finance_enabled', sa.Boolean(), nullable=False),
    sa.Column('module_warehouse_enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.execute(
        sa.text(
            "INSERT INTO companies (id, name, module_finance_enabled, module_warehouse_enabled, created_at) "
            "VALUES (:id, 'Щёлоковъ', true, true, now())"
        ).bindparams(id=COMPANY_1_ID)
    )


def downgrade() -> None:
    op.drop_table('companies')
