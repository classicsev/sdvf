"""foundation fields for future bilingual RU/China trade documents (contract/invoice/packing list)

Revision ID: b3f7e5a92c14
Revises: a1c5f8b3e027
Create Date: 2026-08-21 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b3f7e5a92c14"
down_revision = "a1c5f8b3e027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("counterparties", sa.Column("cn_name_zh", sa.String(length=300), nullable=True))
    op.add_column("counterparties", sa.Column("cn_credit_code", sa.String(length=32), nullable=True))
    op.add_column("counterparties", sa.Column("cn_legal_rep", sa.String(length=200), nullable=True))
    op.add_column("counterparties", sa.Column("cn_address_zh", sa.Text(), nullable=True))

    op.add_column("orders", sa.Column("incoterms", sa.String(length=10), nullable=True))
    op.add_column("orders", sa.Column("incoterms_place", sa.String(length=200), nullable=True))
    op.add_column("orders", sa.Column("payment_terms", sa.Text(), nullable=True))

    op.add_column("order_lines", sa.Column("package_count", sa.Integer(), nullable=True))
    op.add_column("order_lines", sa.Column("package_type", sa.String(length=50), nullable=True))
    op.add_column("order_lines", sa.Column("gross_weight", sa.Numeric(12, 3), nullable=True))
    op.add_column("order_lines", sa.Column("net_weight", sa.Numeric(12, 3), nullable=True))
    op.add_column("order_lines", sa.Column("marks", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_lines", "marks")
    op.drop_column("order_lines", "net_weight")
    op.drop_column("order_lines", "gross_weight")
    op.drop_column("order_lines", "package_type")
    op.drop_column("order_lines", "package_count")

    op.drop_column("orders", "payment_terms")
    op.drop_column("orders", "incoterms_place")
    op.drop_column("orders", "incoterms")

    op.drop_column("counterparties", "cn_address_zh")
    op.drop_column("counterparties", "cn_legal_rep")
    op.drop_column("counterparties", "cn_credit_code")
    op.drop_column("counterparties", "cn_name_zh")
