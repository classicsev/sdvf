"""add users.phone/email_verified, nullable password/email for OAuth-only accounts, oauth_accounts table

Revision ID: a3f5e9d2c1b7
Revises: 9e2b7c4f1a8d
Create Date: 2026-08-07 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3f5e9d2c1b7'
down_revision = '9e2b7c4f1a8d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Поле для модели User уже существовало в коде (без миграции) — добавляем
    # колонку теперь, вместе с остальными изменениями этой фазы.
    op.add_column('users', sa.Column('phone', sa.String(length=30), nullable=True))

    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=True))
    # Уже существующие пользователи (в т.ч. реальный админ на проде) реально
    # пользуются аккаунтом без какой-либо проверки — им незачем подтверждать
    # то, чем уже пользуются; помечаем их подтверждёнными задним числом.
    op.execute("UPDATE users SET email_verified = true WHERE email_verified IS NULL")
    op.alter_column('users', 'email_verified', nullable=False, server_default=sa.false())

    # Nullable — у чисто-OAuth пользователей (VK ID и т.п.) пароля нет, а VK ID
    # не всегда отдаёт email. Уникальность email не снимается — Postgres UNIQUE
    # разрешает сколько угодно NULL, конфликтов между OAuth-пользователями без
    # email это не создаст.
    op.alter_column('users', 'hashed_password', existing_type=sa.String(length=255), nullable=True)
    op.alter_column('users', 'email', existing_type=sa.String(length=255), nullable=True)

    op.create_table(
        'oauth_accounts',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('provider_user_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_user_id', name='uq_oauth_accounts_provider_user'),
    )
    op.create_index('ix_oauth_accounts_user_id', 'oauth_accounts', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_oauth_accounts_user_id', table_name='oauth_accounts')
    op.drop_table('oauth_accounts')

    op.alter_column('users', 'email', existing_type=sa.String(length=255), nullable=False)
    op.alter_column('users', 'hashed_password', existing_type=sa.String(length=255), nullable=False)
    op.drop_column('users', 'email_verified')
    op.drop_column('users', 'phone')
