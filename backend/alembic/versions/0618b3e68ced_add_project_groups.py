"""add project groups (hierarchy above project)

Revision ID: 0618b3e68ced
Revises: b3f7e5a92c14
Create Date: 2026-08-21

Группа проектов — уровень выше Project (например, «Пчёлы» как сезонное
направление, внутри которого заводятся проекты по месяцам). Без
cross-company is_global/visible_companies — см. models.py::ProjectGroup.
Существующие проекты остаются без группы (group_id nullable) — старые
данные (в т.ч. «Пчёлы») намеренно не мигрируются.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0618b3e68ced"
down_revision = "b3f7e5a92c14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_groups",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "projects",
        sa.Column("group_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_groups.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "group_id")
    op.drop_table("project_groups")
