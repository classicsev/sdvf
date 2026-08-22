"""project group multi-company scope (is_global + M2M visibility)

Revision ID: 46e1df8abff8
Revises: 8169d988ba60
Create Date: 2026-08-22

Группы проектов раньше были видны только в своей компании — единственный
справочник без кросс-компанийной видимости, в отличие от Category/Project.
Приводим к тому же паттерну (см. f2a7c4e91b36_category_project_multi_company.py).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "46e1df8abff8"
down_revision = "8169d988ba60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_groups", sa.Column("is_global", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "project_group_companies",
        sa.Column("project_group_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_groups.id"), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("project_group_companies")
    op.drop_column("project_groups", "is_global")
