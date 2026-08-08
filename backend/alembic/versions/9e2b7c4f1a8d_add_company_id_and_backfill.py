"""add company_id to all tables and backfill to Компания №1 (мультитенантность)

Revision ID: 9e2b7c4f1a8d
Revises: 8d4f1a6c2b9e
Create Date: 2026-08-07 14:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9e2b7c4f1a8d'
down_revision = '8d4f1a6c2b9e'
branch_labels = None
depends_on = None

COMPANY_1_ID = '2c7cc73f-9bc7-431f-9084-277a65d1ece8'

TABLES = [
    "accounts", "categories", "projects", "counterparties", "employees", "users",
    "transactions", "planning", "payroll_accruals", "payroll_payments",
    "warehouses", "products", "product_variants", "stock_movements",
    "orders", "order_lines", "production_recipes", "production_recipe_inputs", "production_runs",
    "automation_rules", "integrations", "api_keys", "audit_log",
]


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column('company_id', sa.UUID(as_uuid=False), nullable=True))
        op.execute(
            sa.text(f"UPDATE {table} SET company_id = :cid WHERE company_id IS NULL")
            .bindparams(cid=COMPANY_1_ID)
        )
        # server_default оставляет старый код (до деплоя роутеров, знающих про
        # company_id) рабочим без изменений — новые INSERT'ы от него по-прежнему
        # проходят, попадая в Компанию №1. Это то, что позволяет выкатить эту
        # миграцию отдельным безопасным no-op деплоем, до кода Фазы Б.
        op.alter_column(table, 'company_id', nullable=False, server_default=COMPANY_1_ID)
        op.create_foreign_key(f'fk_{table}_company_id', table, 'companies', ['company_id'], ['id'])
        op.create_index(f'ix_{table}_company_id', table, ['company_id'])

    op.drop_constraint('uq_transactions_external_ref', 'transactions', type_='unique')
    op.create_unique_constraint(
        'uq_transactions_company_id_external_ref', 'transactions', ['company_id', 'external_ref']
    )


def downgrade() -> None:
    op.drop_constraint('uq_transactions_company_id_external_ref', 'transactions', type_='unique')
    op.create_unique_constraint('uq_transactions_external_ref', 'transactions', ['external_ref'])

    for table in reversed(TABLES):
        op.drop_index(f'ix_{table}_company_id', table_name=table)
        op.drop_constraint(f'fk_{table}_company_id', table, type_='foreignkey')
        op.drop_column(table, 'company_id')
