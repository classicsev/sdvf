"""project budget lines

Revision ID: c9e4a71d5f83
Revises: b7d3f19a4c62
Create Date: 2026-08-24

Плоский план по статье внутри проекта — "источник плана: Бюджет" в новой
карточке проекта (см. HANDOVER.md, "Карточка проекта"). Второй источник
плана ("Операции") ничего не хранит отдельно — переиспользует уже
существующие payment_confirmed/accrual_confirmed флаги на Transaction.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9e4a71d5f83"
down_revision = "b7d3f19a4c62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_budget_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("categories.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint("project_id", "category_id", name="uq_project_budget_lines_project_category"),
    )


def downgrade() -> None:
    op.drop_table("project_budget_lines")
