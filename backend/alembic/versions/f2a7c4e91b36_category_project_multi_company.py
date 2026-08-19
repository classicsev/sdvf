"""category/project multi-company scope (is_global + M2M visibility)

Revision ID: f2a7c4e91b36
Revises: d5f9b1c7e284
Create Date: 2026-08-19

Статья/проект по умолчанию видны только в своей company_id (как и раньше) —
is_global=false, пустые *_companies. Новое: is_global=true делает запись
видимой динамически во всех компаниях холдинга (включая будущие), а строки
в category_companies/project_companies — видимой в конкретных ДОПОЛНИТЕЛЬНЫХ
компаниях, когда is_global=false. См. routers/reference.py.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2a7c4e91b36"
down_revision = "d5f9b1c7e284"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("is_global", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("projects", sa.Column("is_global", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "category_companies",
        sa.Column("category_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("categories.id"), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), primary_key=True),
    )
    op.create_table(
        "project_companies",
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("project_companies")
    op.drop_table("category_companies")
    op.drop_column("projects", "is_global")
    op.drop_column("categories", "is_global")
