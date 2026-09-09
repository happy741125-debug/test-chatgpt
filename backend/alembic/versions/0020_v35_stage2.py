"""V3.5 stage 2 operational imports and weekly manual inputs.

Revision ID: 0020_v35_stage2
Revises: 0019_repair_history_snapshots
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_v35_stage2"
down_revision: str | None = "0019_repair_history_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gowarehouse_operational_records",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("warehouse", sa.String(length=120), nullable=True),
        sa.Column("channel", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=True),
        sa.Column("planned_quantity", sa.Integer(), nullable=False),
        sa.Column("accepted_quantity", sa.Integer(), nullable=False),
        sa.Column("completed_quantity", sa.Integer(), nullable=False),
        sa.Column("shipment_count", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["gowarehouse_import_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gw_operational_kind_date",
        "gowarehouse_operational_records",
        ["kind", "occurred_on"],
    )
    op.create_index(
        "ix_gw_operational_warehouse", "gowarehouse_operational_records", ["warehouse"]
    )
    op.create_table(
        "weekly_operations_inputs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("warehouse", sa.String(length=80), nullable=False),
        sa.Column("labor_hours", sa.Float(), nullable=True),
        sa.Column("processing_quantity", sa.Integer(), nullable=True),
        sa.Column("consumables_inventory_note", sa.Text(), nullable=True),
        sa.Column("inventory_count_quantity", sa.Integer(), nullable=True),
        sa.Column("inventory_variance_quantity", sa.Integer(), nullable=True),
        sa.Column("pallet_placement_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "week_start", "warehouse", name="uq_weekly_operations_week_warehouse"
        ),
    )
    op.create_index("ix_weekly_operations_week", "weekly_operations_inputs", ["week_start"])


def downgrade() -> None:
    op.drop_index("ix_weekly_operations_week", table_name="weekly_operations_inputs")
    op.drop_table("weekly_operations_inputs")
    op.drop_index("ix_gw_operational_warehouse", table_name="gowarehouse_operational_records")
    op.drop_index("ix_gw_operational_kind_date", table_name="gowarehouse_operational_records")
    op.drop_table("gowarehouse_operational_records")
