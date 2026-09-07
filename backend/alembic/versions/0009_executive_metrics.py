"""Add persistent CEO cockpit metric snapshots.

Revision ID: 0009_executive_metrics
Revises: 0008_reclassify_legacy_outbound
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_executive_metrics"
down_revision: str | None = "0008_reclassify_legacy_outbound"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "executive_metric_snapshots",
        sa.Column("metric_code", sa.String(length=50), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("health_status", sa.String(length=20), nullable=False),
        sa.Column("period_label", sa.String(length=80), nullable=True),
        sa.Column("source_label", sa.String(length=120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("metric_code"),
    )


def downgrade() -> None:
    op.drop_table("executive_metric_snapshots")
