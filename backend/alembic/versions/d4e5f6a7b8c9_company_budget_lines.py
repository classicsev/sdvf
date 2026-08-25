"""company budget lines (БДДС/БДР)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-25

Компанийный (не привязанный к проекту) план по статье на месяц — БДДС/БДР.
Тот же плоский шаблон, что project_budget_lines, но с обязательным period
вместо project_id (см. models.py::CompanyBudgetLine докстринг).
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_budget_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("categories.id"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint(
            "company_id", "category_id", "period", name="uq_company_budget_lines_company_category_period"
        ),
    )


def downgrade() -> None:
    op.drop_table("company_budget_lines")
