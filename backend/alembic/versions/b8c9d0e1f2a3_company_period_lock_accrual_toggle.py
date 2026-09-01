"""company period lock + accrual date field toggle

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-01

По образцу ПланФакт (см. HANDOVER.md, "Дата начисления + закрытие
периода"): show_accrual_date_field — скрывает поле "Дата начисления" в
форме операции, дата начисления тогда молча равна дате оплаты;
locked_before_date — операции с датой оплаты/начисления на эту дату или
раньше нельзя создать/изменить/удалить вручную (см.
transactions.py::_check_not_locked).
"""

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("show_accrual_date_field", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("companies", sa.Column("locked_before_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "locked_before_date")
    op.drop_column("companies", "show_accrual_date_field")
