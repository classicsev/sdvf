"""counterparty requisites + contacts + sdvf/amocrm links

Revision ID: f1a4c8d20b57
Revises: e5f9a2b7c614
Create Date: 2026-08-15

Карточка контрагента становится карточкой организации (реквизиты как у Buyer
в СДВФ) с подвязанными контактными лицами — см. models.py::Counterparty.
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a4c8d20b57"
down_revision = "e5f9a2b7c614"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("counterparties", sa.Column("kpp", sa.String(length=20), nullable=True))
    op.add_column("counterparties", sa.Column("ogrn", sa.String(length=20), nullable=True))
    op.add_column("counterparties", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("counterparties", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("counterparties", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("counterparties", sa.Column("sdvf_buyer_id", sa.Integer(), nullable=True))
    op.add_column("counterparties", sa.Column("sdvf_synced_at", sa.DateTime(), nullable=True))
    op.add_column("counterparties", sa.Column("amocrm_company_id", sa.BigInteger(), nullable=True))

    op.create_table(
        "counterparty_contacts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column(
            "counterparty_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("counterparties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(length=300), nullable=False),
        sa.Column("position", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("amocrm_contact_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_counterparty_contacts_counterparty_id", "counterparty_contacts", ["counterparty_id"])
    # Повторный синк amoCRM не должен плодить дубли одного и того же контакта;
    # уникальность в рамках компании, а не глобально — один и тот же контакт амо
    # может быть заведён в разных компаниях холдинга независимо.
    op.create_index(
        "uq_counterparty_contacts_amocrm",
        "counterparty_contacts",
        ["company_id", "amocrm_contact_id"],
        unique=True,
        postgresql_where=sa.text("amocrm_contact_id IS NOT NULL"),
    )
    # Одна карточка СДВФ — не больше одной карточки в рамках компании Учёта,
    # иначе документы уйдут не на того контрагента.
    op.create_index(
        "uq_counterparties_sdvf_buyer",
        "counterparties",
        ["company_id", "sdvf_buyer_id"],
        unique=True,
        postgresql_where=sa.text("sdvf_buyer_id IS NOT NULL"),
    )
    op.create_index(
        "uq_counterparties_amocrm_company",
        "counterparties",
        ["company_id", "amocrm_company_id"],
        unique=True,
        postgresql_where=sa.text("amocrm_company_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_counterparties_amocrm_company", table_name="counterparties")
    op.drop_index("uq_counterparties_sdvf_buyer", table_name="counterparties")
    op.drop_index("uq_counterparty_contacts_amocrm", table_name="counterparty_contacts")
    op.drop_index("ix_counterparty_contacts_counterparty_id", table_name="counterparty_contacts")
    op.drop_table("counterparty_contacts")

    op.drop_column("counterparties", "amocrm_company_id")
    op.drop_column("counterparties", "sdvf_synced_at")
    op.drop_column("counterparties", "sdvf_buyer_id")
    op.drop_column("counterparties", "email")
    op.drop_column("counterparties", "phone")
    op.drop_column("counterparties", "address")
    op.drop_column("counterparties", "ogrn")
    op.drop_column("counterparties", "kpp")
