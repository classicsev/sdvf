"""category is_financing flag

Revision ID: c4a8e2f6b913
Revises: b7e3c9f1a24d
Create Date: 2026-08-18

Кредитные линии/займы и их погашение — финансовая, не операционная деятельность
(не входит в налогооблагаемую базу ни при УСН-доходы, ни при ОСН). См.
routers/reports.py (dashboard_summary, pnl_report) и integrations/tbank.py.
"""

import sqlalchemy as sa
from alembic import op

revision = "c4a8e2f6b913"
down_revision = "b7e3c9f1a24d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("is_financing", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("categories", "is_financing")
