"""multi-company: add company_members (M2M user<->company), companies.owner_user_id/
company_type, drop users.company_id/role/project_id (см. план "Мульти-компании")

Revision ID: e5f9a2b7c614
Revises: d8e6a1c4b9f3
Create Date: 2026-08-11 01:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'e5f9a2b7c614'
down_revision = 'd8e6a1c4b9f3'
branch_labels = None
depends_on = None

roleenum = postgresql.ENUM(
    'admin', 'operator', 'payroll_operator', 'project_manager', 'viewer', 'warehouse_operator',
    name='roleenum',
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        'company_members',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', roleenum, nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'company_id', name='uq_company_member_user_company'),
    )
    op.create_index('ix_company_members_user_id', 'company_members', ['user_id'])
    op.create_index('ix_company_members_company_id', 'company_members', ['company_id'])

    op.add_column('companies', sa.Column('owner_user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('companies', sa.Column('company_type', sa.String(length=20), nullable=False, server_default='legal_entity'))

    # Data-миграция: у каждого существующего пользователя ровно одна компания —
    # переносим её как единственное членство.
    op.execute(
        """
        INSERT INTO company_members (id, user_id, company_id, role, project_id, created_at)
        SELECT gen_random_uuid(), id, company_id, role, project_id, now()
        FROM users
        """
    )
    op.execute(
        """
        UPDATE companies
        SET owner_user_id = (
            SELECT user_id FROM company_members WHERE company_members.company_id = companies.id LIMIT 1
        )
        """
    )

    op.drop_column('users', 'company_id')
    op.drop_column('users', 'role')
    op.drop_column('users', 'project_id')


def downgrade() -> None:
    op.add_column('users', sa.Column('company_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('users', sa.Column('role', roleenum, nullable=True))
    op.add_column('users', sa.Column('project_id', postgresql.UUID(as_uuid=False), nullable=True))

    op.execute(
        """
        UPDATE users
        SET company_id = cm.company_id, role = cm.role, project_id = cm.project_id
        FROM (
            SELECT DISTINCT ON (user_id) user_id, company_id, role, project_id
            FROM company_members
            ORDER BY user_id, created_at
        ) cm
        WHERE users.id = cm.user_id
        """
    )

    op.alter_column('users', 'company_id', nullable=False)
    op.alter_column('users', 'role', nullable=False)
    op.create_foreign_key('users_company_id_fkey', 'users', 'companies', ['company_id'], ['id'])
    op.create_foreign_key('users_project_id_fkey', 'users', 'projects', ['project_id'], ['id'])

    op.drop_column('companies', 'company_type')
    op.drop_column('companies', 'owner_user_id')

    op.drop_index('ix_company_members_company_id', table_name='company_members')
    op.drop_index('ix_company_members_user_id', table_name='company_members')
    op.drop_table('company_members')
