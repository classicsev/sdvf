"""add sdvf integration fields: orders.sdvf_invoice_ref/sdvf_utd_ref, companies.sdvf_auto_generate_documents

Revision ID: f2c8e5a19d34
Revises: a3f5e9d2c1b7
Create Date: 2026-08-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f2c8e5a19d34'
down_revision = 'a3f5e9d2c1b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('sdvf_invoice_ref', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('orders', sa.Column('sdvf_utd_ref', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(
        'companies',
        sa.Column('sdvf_auto_generate_documents', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('companies', 'sdvf_auto_generate_documents')
    op.drop_column('orders', 'sdvf_utd_ref')
    op.drop_column('orders', 'sdvf_invoice_ref')
