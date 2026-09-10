"""Add warehouse and merchant governance for controlled imports.

Revision ID: 0022_upload_data_governance
Revises: 0021_admin_credentials
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0022_upload_data_governance"
down_revision: str | None = "0021_admin_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    now = datetime.now(UTC)
    warehouses = op.create_table(
        "warehouse_masters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("aliases_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "merchant_masters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("aliases_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.bulk_insert(
        warehouses,
        [
            {
                "id": "warehouse-tamsui",
                "code": "TAMSUI",
                "name": "淡水倉",
                "aliases_json": ["淡水", "淡水倉庫"],
                "status": "ACTIVE",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "warehouse-xizhi",
                "code": "XIZHI",
                "name": "汐止倉",
                "aliases_json": ["汐止", "汐止倉庫"],
                "status": "ACTIVE",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )

    with op.batch_alter_table("gowarehouse_import_batches") as batch:
        batch.add_column(sa.Column("merchant_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("warehouse_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="IMPORTED"
            )
        )
        batch.add_column(
            sa.Column("detection_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch.add_column(sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_gw_batch_merchant", "merchant_masters", ["merchant_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_gw_batch_warehouse", "warehouse_masters", ["warehouse_id"], ["id"]
        )

    for table in ("gowarehouse_orders", "gowarehouse_inventory"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("merchant_id", sa.String(length=36), nullable=True))
            batch.add_column(sa.Column("warehouse", sa.String(length=120), nullable=True))
            batch.add_column(sa.Column("warehouse_id", sa.String(length=36), nullable=True))
            batch.create_foreign_key(
                f"fk_{table}_merchant", "merchant_masters", ["merchant_id"], ["id"]
            )
            batch.create_foreign_key(
                f"fk_{table}_warehouse", "warehouse_masters", ["warehouse_id"], ["id"]
            )

    with op.batch_alter_table("gowarehouse_operational_records") as batch:
        batch.add_column(sa.Column("merchant", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("merchant_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("warehouse_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("order_ref_hash", sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            "fk_gw_operational_merchant", "merchant_masters", ["merchant_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_gw_operational_warehouse", "warehouse_masters", ["warehouse_id"], ["id"]
        )
        batch.create_index("ix_gw_operational_order_ref", ["order_ref_hash"])

    op.create_table(
        "gowarehouse_import_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=24), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["gowarehouse_import_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gw_import_change_batch",
        "gowarehouse_import_changes",
        ["batch_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_gw_import_change_batch", table_name="gowarehouse_import_changes")
    op.drop_table("gowarehouse_import_changes")
    with op.batch_alter_table("gowarehouse_operational_records") as batch:
        batch.drop_index("ix_gw_operational_order_ref")
        batch.drop_constraint("fk_gw_operational_warehouse", type_="foreignkey")
        batch.drop_constraint("fk_gw_operational_merchant", type_="foreignkey")
        batch.drop_column("order_ref_hash")
        batch.drop_column("warehouse_id")
        batch.drop_column("merchant_id")
        batch.drop_column("merchant")
    for table in ("gowarehouse_inventory", "gowarehouse_orders"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_warehouse", type_="foreignkey")
            batch.drop_constraint(f"fk_{table}_merchant", type_="foreignkey")
            batch.drop_column("warehouse_id")
            batch.drop_column("warehouse")
            batch.drop_column("merchant_id")
    with op.batch_alter_table("gowarehouse_import_batches") as batch:
        batch.drop_constraint("fk_gw_batch_warehouse", type_="foreignkey")
        batch.drop_constraint("fk_gw_batch_merchant", type_="foreignkey")
        batch.drop_column("undone_at")
        batch.drop_column("confirmed_at")
        batch.drop_column("detection_json")
        batch.drop_column("status")
        batch.drop_column("warehouse_id")
        batch.drop_column("merchant_id")
    op.drop_table("merchant_masters")
    op.drop_table("warehouse_masters")
