"""add users.avatar_url/telegram/max_messenger/gender (profile fields, mirrors СДВФ)

Revision ID: d8e6a1c4b9f3
Revises: c7b3f8a04e21
Create Date: 2026-08-11 00:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd8e6a1c4b9f3'
down_revision = 'c7b3f8a04e21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('telegram', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('max_messenger', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('gender', sa.String(length=1), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'gender')
    op.drop_column('users', 'max_messenger')
    op.drop_column('users', 'telegram')
    op.drop_column('users', 'avatar_url')
