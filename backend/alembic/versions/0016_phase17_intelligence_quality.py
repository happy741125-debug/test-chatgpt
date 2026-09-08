"""Add lifecycle signals, change history, and human feedback.

Revision ID: 0016_phase17_quality
Revises: 0015_phase15_16_quality
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_phase17_quality"
down_revision: str | None = "0015_phase15_16_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "intelligence_objects",
        sa.Column(
            "lifecycle_stage",
            sa.String(length=40),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "intelligence_objects",
        sa.Column("blocker_type", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "intelligence_objects",
        sa.Column(
            "attention_locked", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "intelligence_objects",
        sa.Column("change_kind", sa.String(length=30), nullable=False, server_default="NEW"),
    )
    op.add_column(
        "intelligence_objects",
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "intelligence_objects",
        sa.Column(
            "last_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute("UPDATE intelligence_objects SET last_changed_at = created_at")
    op.create_table(
        "intelligence_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_id", sa.String(length=36), nullable=False),
        sa.Column("field_name", sa.String(length=60), nullable=False),
        sa.Column("previous_value_json", sa.JSON(), nullable=True),
        sa.Column("corrected_value_json", sa.JSON(), nullable=False),
        sa.Column("actor_text", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["intelligence_id"], ["intelligence_objects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intelligence_feedback_card_created",
        "intelligence_feedback",
        ["intelligence_id", "created_at"],
    )
    op.create_table(
        "intelligence_change_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_id", sa.String(length=36), nullable=False),
        sa.Column("change_kind", sa.String(length=30), nullable=False),
        sa.Column("previous_stage", sa.String(length=40), nullable=True),
        sa.Column("current_stage", sa.String(length=40), nullable=True),
        sa.Column("blocker_type", sa.String(length=60), nullable=True),
        sa.Column("evidence_message_ids_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["intelligence_id"], ["intelligence_objects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intelligence_change_card_created",
        "intelligence_change_audits",
        ["intelligence_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_intelligence_change_card_created", table_name="intelligence_change_audits")
    op.drop_table("intelligence_change_audits")
    op.drop_index("ix_intelligence_feedback_card_created", table_name="intelligence_feedback")
    op.drop_table("intelligence_feedback")
    op.drop_column("intelligence_objects", "last_changed_at")
    op.drop_column("intelligence_objects", "occurrence_count")
    op.drop_column("intelligence_objects", "change_kind")
    op.drop_column("intelligence_objects", "blocker_type")
    op.drop_column("intelligence_objects", "attention_locked")
    op.drop_column("intelligence_objects", "lifecycle_stage")
