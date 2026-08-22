"""employee aliases — прозвища/сокращения для резолва при синке со Sheets

Revision ID: d4e91a6c3f72
Revises: c3d7f92a5e18
Create Date: 2026-08-22

Реальные листы пишут сокращённые имена ("Женя Цихм" вместо "Женя
Цихмейструк") — без явного алиаса это создавало бы дубль сотрудника
вместо резолва существующего.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e91a6c3f72"
down_revision = "c3d7f92a5e18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("aliases", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "aliases")
