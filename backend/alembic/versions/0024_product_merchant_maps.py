"""Add governed product-to-merchant mappings.

Revision ID: 0024_product_merchant_maps
Revises: 0023_pending_merchant_imports
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_product_merchant_maps"
down_revision: str | None = "0023_pending_merchant_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gowarehouse_product_merchant_maps",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("merchant_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_kinds_json", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchant_masters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_index(
        "ix_gw_product_map_status",
        "gowarehouse_product_merchant_maps",
        ["status", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gw_product_map_status",
        table_name="gowarehouse_product_merchant_maps",
    )
    op.drop_table("gowarehouse_product_merchant_maps")
