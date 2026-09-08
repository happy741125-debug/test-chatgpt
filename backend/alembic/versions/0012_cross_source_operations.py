"""Add payment taxonomy and normalized operational performance data.

Revision ID: 0012_cross_source_operations
Revises: 0011_revenue_dashboard
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0012_cross_source_operations"
down_revision: str | None = "0011_revenue_dashboard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    event_types = sa.table(
        "event_types",
        sa.column("code", sa.String),
        sa.column("domain_code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        event_types,
        [
            {
                "code": "PAYMENT_STATUS",
                "domain_code": "FINANCE_COST",
                "name": "收款／對帳狀態",
                "description": "匯款、付款、應收款、對帳與入帳進度",
                "active": True,
                "created_at": datetime.now(UTC),
            }
        ],
    )
    op.create_table(
        "operational_import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256"),
    )
    op.create_table(
        "operational_order_records",
        sa.Column("order_id", sa.String(length=120), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("warehouse", sa.String(length=80), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("promised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("urgent", sa.Boolean(), nullable=False),
        sa.Column("exception_count", sa.Integer(), nullable=False),
        sa.Column("processing_minutes", sa.Integer(), nullable=True),
        sa.Column("worker_hours", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["operational_import_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("order_id"),
    )
    op.create_index(
        "ix_operational_order_date", "operational_order_records", ["order_date"], unique=False
    )
    op.create_index(
        "ix_operational_warehouse_date",
        "operational_order_records",
        ["warehouse", "order_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_operational_warehouse_date", table_name="operational_order_records")
    op.drop_index("ix_operational_order_date", table_name="operational_order_records")
    op.drop_table("operational_order_records")
    op.drop_table("operational_import_batches")
    op.execute("DELETE FROM event_types WHERE code = 'PAYMENT_STATUS'")
