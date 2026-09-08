"""Add attachment evidence and conservative case review records.

Revision ID: 0015_phase15_16_quality
Revises: 0014_attention_status_audit
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_phase15_16_quality"
down_revision: str | None = "0014_attention_status_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("external_attachment_id", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("sensitive_level", sa.String(length=20), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id", "external_attachment_id", name="uq_attachment_message_external"
        ),
    )
    op.create_index(
        "ix_attachments_status_created", "attachments", ["processing_status", "created_at"]
    )
    op.create_table(
        "attachment_access_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attachment_id", sa.String(length=36), nullable=False),
        sa.Column("actor_text", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attachment_access_created",
        "attachment_access_audits",
        ["attachment_id", "created_at"],
    )
    op.create_table(
        "case_review_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_intelligence_id", sa.String(length=36), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolution", sa.String(length=40), nullable=True),
        sa.Column("actor_text", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_intelligence_id"], ["intelligence_objects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["intelligence_id"], ["intelligence_objects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "intelligence_id", "candidate_intelligence_id", name="uq_case_review_pair"
        ),
    )
    op.create_index(
        "ix_case_review_status_created", "case_review_items", ["status", "created_at"]
    )
    op.create_table(
        "case_merge_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_intelligence_id", sa.String(length=36), nullable=True),
        sa.Column("target_intelligence_id", sa.String(length=36), nullable=False),
        sa.Column("source_context_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("moved_message_ids_json", sa.JSON(), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("actor_text", sa.String(length=120), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_context_id"], ["contexts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_intelligence_id"], ["intelligence_objects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_intelligence_id"], ["intelligence_objects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_case_merge_target_created",
        "case_merge_audits",
        ["target_intelligence_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_merge_target_created", table_name="case_merge_audits")
    op.drop_table("case_merge_audits")
    op.drop_index("ix_case_review_status_created", table_name="case_review_items")
    op.drop_table("case_review_items")
    op.drop_index("ix_attachment_access_created", table_name="attachment_access_audits")
    op.drop_table("attachment_access_audits")
    op.drop_index("ix_attachments_status_created", table_name="attachments")
    op.drop_table("attachments")
