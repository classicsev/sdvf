"""transaction category/project splits — разбивка одной операции на несколько статей/проектов

Revision ID: c1d2e3f4a5b6
Revises: b8c9d0e1f2a3
Create Date: 2026-09-09

Пользователь: платёж на несколько проектов/статей (напр. доставка в
аэропорт для нескольких заказов) должен разбиваться в статистике по
каждому, без создания лишних строк в списке операций. Две новые таблицы
"долей", независимые друг от друга — существуют только когда операция
реально разбита на 2+; для обычных операций transactions.category_id
работает как раньше. transactions.category_id становится nullable —
NULL означает "смотри в transaction_category_splits".
"""

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None

_UUID = sa.dialects.postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.alter_column("transactions", "category_id", nullable=True)

    op.create_table(
        "transaction_category_splits",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "transaction_id",
            _UUID,
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_id", _UUID, sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount_rub", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index(
        "ix_transaction_category_splits_transaction_id",
        "transaction_category_splits",
        ["transaction_id"],
    )
    op.create_index(
        "ix_transaction_category_splits_category_id",
        "transaction_category_splits",
        ["category_id"],
    )

    op.create_table(
        "transaction_project_splits",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "transaction_id",
            _UUID,
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", _UUID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount_rub", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index(
        "ix_transaction_project_splits_transaction_id",
        "transaction_project_splits",
        ["transaction_id"],
    )
    op.create_index(
        "ix_transaction_project_splits_project_id",
        "transaction_project_splits",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_table("transaction_project_splits")
    op.drop_table("transaction_category_splits")
    op.alter_column("transactions", "category_id", nullable=False)
