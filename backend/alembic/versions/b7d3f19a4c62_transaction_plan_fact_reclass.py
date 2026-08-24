"""transaction plan/fact confirmation + reclass pair

Revision ID: b7d3f19a4c62
Revises: a6c2e8f47d19
Create Date: 2026-08-24

План/факт по двум независимым измерениям (см. HANDOVER.md, "План/факт
(ПланФакт-стиль)"): payment_confirmed (деньги реально пришли/ушли) и
accrual_confirmed (услуга/товар реально оказаны/отгружены) — отчёты/остаток
фильтруются по нужному измерению, см. reports.py. server_default=true —
существующие операции остаются фактом без изменения поведения.

reclass_pair_id — связывает две ноги операции "Начисление" (перенос суммы
между статьями без движения денег, см. POST /transactions/reclass),
отдельно от transfer_pair_id (там деньги реально двигались).
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d3f19a4c62"
down_revision = "a6c2e8f47d19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("payment_confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "transactions",
        sa.Column("accrual_confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "transactions",
        sa.Column("reclass_pair_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "reclass_pair_id")
    op.drop_column("transactions", "accrual_confirmed")
    op.drop_column("transactions", "payment_confirmed")
