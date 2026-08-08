"""add companies.sdvf_org_* fields (our own legal details for СДВФ InformationOrganization)

Revision ID: c7b3f8a04e21
Revises: f2c8e5a19d34
Create Date: 2026-08-08 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7b3f8a04e21'
down_revision = 'f2c8e5a19d34'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('sdvf_org_naming', sa.String(length=300), nullable=True))
    op.add_column('companies', sa.Column('sdvf_org_inn', sa.String(length=20), nullable=True))
    op.add_column('companies', sa.Column('sdvf_org_kpp', sa.String(length=20), nullable=True))
    op.add_column('companies', sa.Column('sdvf_org_ogrn', sa.String(length=20), nullable=True))
    op.add_column('companies', sa.Column('sdvf_org_address', sa.Text(), nullable=True))
    op.add_column('companies', sa.Column('sdvf_org_phone', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'sdvf_org_phone')
    op.drop_column('companies', 'sdvf_org_address')
    op.drop_column('companies', 'sdvf_org_ogrn')
    op.drop_column('companies', 'sdvf_org_kpp')
    op.drop_column('companies', 'sdvf_org_inn')
    op.drop_column('companies', 'sdvf_org_naming')
