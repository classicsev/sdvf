"""transaction transfer_pair_id

Revision ID: a6c2e8f47d19
Revises: e5f3a08c7b41
Create Date: 2026-08-24

Операция "Перемещение" (перевод между своими же счетами) создаёт ДВЕ строки
Transaction (списание с одного счёта + зачисление на другой), помеченные уже
существующими категориями is_internal_transfer=True (исключены из П&Л, см.
app/holding_transfers.py) — transfer_pair_id связывает эти две строки друг с
другом, чтобы удаление/отображение одной части сразу находило вторую.
"""

import sqlalchemy as sa
from alembic import op

revision = "a6c2e8f47d19"
down_revision = "e5f3a08c7b41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("transfer_pair_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "transfer_pair_id")
