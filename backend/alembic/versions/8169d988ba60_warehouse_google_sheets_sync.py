"""warehouse google sheets sync (connection + tabs)

Revision ID: 8169d988ba60
Revises: 0618b3e68ced
Create Date: 2026-08-21

Двусторонняя синхронизация склада с Google Таблицами — см. models.py::
WarehouseSheetConnection/WarehouseSheetTab. Один service-account ключ на
компанию (WarehouseSheetConnection), привязанные листы (WarehouseSheetTab)
могут указывать на разные spreadsheet_id (легаси реальная таблица + новая
таблица-шаблон).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8169d988ba60"
down_revision = "0618b3e68ced"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_sheet_connections",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("is_connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("autosync_interval_minutes", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "warehouse_sheet_tabs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("warehouse_sheet_connections.id"),
            nullable=False,
        ),
        sa.Column("spreadsheet_id", sa.String(length=100), nullable=False),
        sa.Column("spreadsheet_label", sa.String(length=200), nullable=True),
        sa.Column("tab_name", sa.String(length=200), nullable=False),
        sa.Column(
            "format",
            sa.Enum(
                "movements",
                "wide_calibers_in",
                "wide_calibers_out",
                "processing_wide",
                name="warehousesheettabformat",
            ),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id"), nullable=True),
        sa.Column(
            "default_warehouse_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("warehouses.id"), nullable=True
        ),
        sa.Column("column_mapping_json", sa.Text(), nullable=True),
        sa.Column("last_synced_row", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("warehouse_sheet_tabs")
    op.drop_table("warehouse_sheet_connections")
    sa.Enum(name="warehousesheettabformat").drop(op.get_bind(), checkfirst=True)
