"""recurring templates

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-25

Повторяющиеся плановые операции — раз в сутки APScheduler-джоб (см.
app/scheduler.py) создаёт обычную Transaction (payment_confirmed=False,
accrual_confirmed=False) из активных шаблонов с next_run_date <= today.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

_tx_type_enum = PGEnum("income", "expense", name="txtypeenum", create_type=False)


def upgrade() -> None:
    recurring_frequency_enum = sa.Enum("weekly", "monthly", name="recurringfrequencyenum")

    op.create_table(
        "recurring_templates",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("type", _tx_type_enum, nullable=False),
        sa.Column("amount_rub", sa.Numeric(14, 2), nullable=False),
        sa.Column("category_id", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("account_id", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column(
            "counterparty_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("counterparties.id"),
            nullable=True,
        ),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("frequency", recurring_frequency_enum, nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=True),
        sa.Column("day_of_month", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("next_run_date", sa.Date, nullable=False),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("recurring_templates")
    sa.Enum(name="recurringfrequencyenum").drop(op.get_bind(), checkfirst=True)
