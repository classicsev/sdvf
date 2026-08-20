"""split comment into comment (user note) + bank_payment_purpose (from bank)

Revision ID: b8e2a4d6c1f3
Revises: a3d7f5c9e1b2
Create Date: 2026-08-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8e2a4d6c1f3'
down_revision = 'a3d7f5c9e1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('bank_payment_purpose', sa.Text(), nullable=True))
    # Импортированные банком операции (external_ref заполнен) до этой миграции
    # писали назначение платежа прямо в comment — своей заметки пользователя
    # там никогда не было (поле было занято банковским текстом целиком), поэтому
    # безопасно перенести целиком, не теряя ничего: comment → bank_payment_purpose,
    # сам comment освобождается под настоящие пользовательские заметки.
    op.execute(
        """
        UPDATE transactions
        SET bank_payment_purpose = comment, comment = NULL
        WHERE external_ref IS NOT NULL AND comment IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE transactions
        SET comment = bank_payment_purpose
        WHERE external_ref IS NOT NULL AND bank_payment_purpose IS NOT NULL AND comment IS NULL
        """
    )
    op.drop_column('transactions', 'bank_payment_purpose')
