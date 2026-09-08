"""Add GoWarehouse orders/inventory import tables.

Revision ID: 0017_gowarehouse_imports
Revises: 0016_phase17_quality
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_gowarehouse_imports"
down_revision: str | None = "0016_phase17_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gowarehouse_import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("merchant", sa.String(length=120), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256"),
    )
    op.create_table(
        "gowarehouse_orders",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("merchant", sa.String(length=120), nullable=False),
        sa.Column("order_id", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=120), nullable=True),
        sa.Column("platform", sa.String(length=120), nullable=True),
        sa.Column("shipping_type", sa.String(length=120), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("urgent", sa.Boolean(), nullable=False),
        sa.Column("reserved_ship_date", sa.Date(), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_status", sa.String(length=60), nullable=True),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["gowarehouse_import_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gw_order_merchant", "gowarehouse_orders", ["merchant"])
    op.create_table(
        "gowarehouse_inventory",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("merchant", sa.String(length=120), nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("inventory_type", sa.String(length=60), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("batch", sa.String(length=120), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=True),
        sa.Column("available", sa.Integer(), nullable=True),
        sa.Column("allocated", sa.Integer(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["gowarehouse_import_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gw_inventory_merchant", "gowarehouse_inventory", ["merchant"])


def downgrade() -> None:
    op.drop_index("ix_gw_inventory_merchant", table_name="gowarehouse_inventory")
    op.drop_table("gowarehouse_inventory")
    op.drop_index("ix_gw_order_merchant", table_name="gowarehouse_orders")
    op.drop_table("gowarehouse_orders")
    op.drop_table("gowarehouse_import_batches")
