"""add companies.module_china_enabled + cn_org_* fields (China legal entity requisites)

Revision ID: a1c5f8b3e027
Revises: b8e2a4d6c1f3
Create Date: 2026-08-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1c5f8b3e027"
down_revision = "b8e2a4d6c1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("module_china_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("companies", sa.Column("cn_org_name_zh", sa.String(length=300), nullable=True))
    op.add_column("companies", sa.Column("cn_org_credit_code", sa.String(length=32), nullable=True))
    op.add_column("companies", sa.Column("cn_org_legal_rep", sa.String(length=200), nullable=True))
    op.add_column("companies", sa.Column("cn_org_address_zh", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("cn_org_registered_capital", sa.Numeric(14, 2), nullable=True))
    op.add_column("companies", sa.Column("cn_org_established_date", sa.Date(), nullable=True))
    op.add_column("companies", sa.Column("cn_org_business_scope_zh", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "cn_org_business_scope_zh")
    op.drop_column("companies", "cn_org_established_date")
    op.drop_column("companies", "cn_org_registered_capital")
    op.drop_column("companies", "cn_org_address_zh")
    op.drop_column("companies", "cn_org_legal_rep")
    op.drop_column("companies", "cn_org_credit_code")
    op.drop_column("companies", "cn_org_name_zh")
    op.drop_column("companies", "module_china_enabled")
