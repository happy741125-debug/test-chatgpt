"""Add canonical AI-COS source records and evidence chain.

Revision ID: 0031_ai_cos_records
Revises: 0030_ai_cos_sources
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_ai_cos_records"
down_revision: str | None = "0030_ai_cos_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("external_record_key", sa.String(length=255), nullable=False),
        sa.Column("record_type", sa.String(length=40), nullable=False),
        sa.Column("content_ref", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=True),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("classification", sa.String(length=30), nullable=False),
        sa.Column("authorization_version", sa.String(length=80), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("normalized_version", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source_registry.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "external_record_key", name="uq_source_record_external"
        ),
        sa.UniqueConstraint(
            "source_id", "idempotency_key", name="uq_source_record_idempotency"
        ),
    )
    op.create_index(
        "ix_source_record_workspace_status",
        "source_records",
        ["workspace_id", "processing_status"],
    )
    op.create_index(
        "ix_source_record_retention", "source_records", ["retention_until"]
    )

    op.create_table(
        "source_record_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_record_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("evidence_ref", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_record_id"], ["source_records.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_record_id", "evidence_ref", name="uq_source_record_evidence_ref"
        ),
    )

    op.create_table(
        "source_record_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_record_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("before_status", sa.String(length=30), nullable=True),
        sa.Column("after_status", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_record_id"], ["source_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_record_audit_created",
        "source_record_audits",
        ["source_record_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_record_audit_created", table_name="source_record_audits")
    op.drop_table("source_record_audits")
    op.drop_table("source_record_evidence")
    op.drop_index("ix_source_record_retention", table_name="source_records")
    op.drop_index("ix_source_record_workspace_status", table_name="source_records")
    op.drop_table("source_records")
