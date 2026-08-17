"""add integration account_id for autosync

Revision ID: b7e3c9f1a24d
Revises: f1a4c8d20b57
Create Date: 2026-08-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'b7e3c9f1a24d'
down_revision = 'f1a4c8d20b57'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # accounts.id — postgresql UUID (см. models.py::gen_uuid/UUID(as_uuid=False)),
    # не String — FK ниже иначе падает с DatatypeMismatch (проверено на проде).
    op.add_column('integrations', sa.Column('account_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column(
        'integrations',
        sa.Column('autosync_enabled', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        'integrations',
        sa.Column('autosync_interval_minutes', sa.Integer(), nullable=False, server_default='60')
    )
    op.create_foreign_key(
        'fk_integrations_account',
        'integrations',
        'accounts',
        ['account_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_integrations_account', 'integrations', type_='foreignkey')
    op.drop_column('integrations', 'autosync_interval_minutes')
    op.drop_column('integrations', 'autosync_enabled')
    op.drop_column('integrations', 'account_id')
