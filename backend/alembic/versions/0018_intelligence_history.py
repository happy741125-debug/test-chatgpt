"""Add append-only intelligence history events and weekly review snapshots.

Revision ID: 0018_intelligence_history
Revises: 0017_gowarehouse_imports
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from alembic import op

revision: str = "0018_intelligence_history"
down_revision: str | None = "0017_gowarehouse_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intelligence_history_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_text", sa.String(length=120), nullable=False),
        sa.Column("evidence_message_ids_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["intelligence_id"], ["intelligence_objects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intelligence_history_occurred", "intelligence_history_events", ["occurred_at"]
    )
    op.create_index(
        "ix_intelligence_history_type_occurred",
        "intelligence_history_events",
        ["event_type", "occurred_at"],
    )
    op.create_index(
        "ix_intelligence_history_card_occurred",
        "intelligence_history_events",
        ["intelligence_id", "occurred_at"],
    )
    op.create_table(
        "weekly_review_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("change_counts_json", sa.JSON(), nullable=False),
        sa.Column("change_event_ids_json", sa.JSON(), nullable=False),
        sa.Column("total_intelligence", sa.Integer(), nullable=False),
        sa.Column("urgent_intelligence", sa.Integer(), nullable=False),
        sa.Column("decisions_needed", sa.Integer(), nullable=False),
        sa.Column("metric_signals_json", sa.JSON(), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_text", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_weekly_review_snapshot_week", "weekly_review_snapshots", ["week_end", "version"]
    )

    # Idempotent backfill from existing cards and audit tables.
    from app.intelligence.backfill import backfill_history_events

    session = Session(bind=op.get_bind())
    try:
        backfill_history_events(session)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    op.drop_index("ix_weekly_review_snapshot_week", table_name="weekly_review_snapshots")
    op.drop_table("weekly_review_snapshots")
    op.drop_index("ix_intelligence_history_card_occurred", table_name="intelligence_history_events")
    op.drop_index("ix_intelligence_history_type_occurred", table_name="intelligence_history_events")
    op.drop_index("ix_intelligence_history_occurred", table_name="intelligence_history_events")
    op.drop_table("intelligence_history_events")
