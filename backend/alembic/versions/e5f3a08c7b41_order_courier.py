"""order courier — кто везёт отгрузку (план "Отгрузки календарь")

Revision ID: e5f3a08c7b41
Revises: d4e91a6c3f72
Create Date: 2026-08-22

Свободнотекстовая пометка, не привязана к Employee/ЗП — только для
дневного календаря заказов, заменяющего ручную таблицу.
"""

import sqlalchemy as sa
from alembic import op

revision = "e5f3a08c7b41"
down_revision = "d4e91a6c3f72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("courier", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "courier")
