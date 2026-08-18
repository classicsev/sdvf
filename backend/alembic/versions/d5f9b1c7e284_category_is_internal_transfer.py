"""category is_internal_transfer flag

Revision ID: d5f9b1c7e284
Revises: c4a8e2f6b913
Create Date: 2026-08-18

Перевод между своими же счетами/компаниями/физлицами в одном холдинге — не
выручка и не расход ни для одной из сторон. См. routers/reports.py
(dashboard_summary, pnl_report) и app/holding_transfers.py.
"""

import sqlalchemy as sa
from alembic import op

revision = "d5f9b1c7e284"
down_revision = "c4a8e2f6b913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("is_internal_transfer", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("categories", "is_internal_transfer")
