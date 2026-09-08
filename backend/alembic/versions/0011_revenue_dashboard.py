"""Add cleaned revenue records and import audit.

Revision ID: 0011_revenue_dashboard
Revises: 0010_weekly_reviews
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_revenue_dashboard"
down_revision: str | None = "0010_weekly_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revenue_import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("period_count", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256"),
    )
    op.create_table(
        "revenue_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("warehouse", sa.String(length=40), nullable=False),
        sa.Column("customer_code", sa.String(length=40), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("source_customer_label", sa.String(length=255), nullable=False),
        sa.Column("warehouse_rent", sa.Numeric(14, 2), nullable=False),
        sa.Column("handling_system", sa.Numeric(14, 2), nullable=False),
        sa.Column("processing", sa.Numeric(14, 2), nullable=False),
        sa.Column("logistics", sa.Numeric(14, 2), nullable=False),
        sa.Column("other", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["revenue_import_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "period",
            "warehouse",
            "source_customer_label",
            name="uq_revenue_period_warehouse_customer",
        ),
    )
    op.create_index("ix_revenue_period", "revenue_records", ["period"], unique=False)
    op.create_index(
        "ix_revenue_customer_period",
        "revenue_records",
        ["customer_code", "period"],
        unique=False,
    )
    op.create_table(
        "revenue_data_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("cell_reference", sa.String(length=80), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("calculated_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("difference", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["revenue_import_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_revenue_issue_period",
        "revenue_data_issues",
        ["period", "severity"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_revenue_issue_period", table_name="revenue_data_issues")
    op.drop_table("revenue_data_issues")
    op.drop_index("ix_revenue_customer_period", table_name="revenue_records")
    op.drop_index("ix_revenue_period", table_name="revenue_records")
    op.drop_table("revenue_records")
    op.drop_table("revenue_import_batches")
