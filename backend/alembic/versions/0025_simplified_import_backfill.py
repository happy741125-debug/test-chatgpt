"""Store non-sensitive product references for automatic merchant backfill.

Revision ID: 0025_simplified_import_backfill
Revises: 0024_product_merchant_maps
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_simplified_import_backfill"
down_revision: str | None = "0024_product_merchant_maps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gowarehouse_orders",
        sa.Column("skus_json", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "gowarehouse_operational_records",
        sa.Column("sku", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gowarehouse_operational_records", "sku")
    op.drop_column("gowarehouse_orders", "skus_json")
