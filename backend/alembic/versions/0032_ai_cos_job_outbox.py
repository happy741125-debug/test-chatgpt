"""Add PostgreSQL-backed job claim leases and workspace traceability.

Revision ID: 0032_ai_cos_job_outbox
Revises: 0031_ai_cos_records
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032_ai_cos_job_outbox"
down_revision: str | None = "0031_ai_cos_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_jobs", sa.Column("workspace_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "processing_jobs", sa.Column("correlation_id", sa.String(length=160), nullable=True)
    )
    op.add_column(
        "processing_jobs", sa.Column("claimed_by", sa.String(length=160), nullable=True)
    )
    op.add_column(
        "processing_jobs", sa.Column("claim_token", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "processing_jobs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_processing_jobs_workspace",
        "processing_jobs",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_jobs_claimable",
        "processing_jobs",
        ["status", "available_at", "claim_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_claimable", table_name="processing_jobs")
    op.drop_constraint(
        "fk_processing_jobs_workspace", "processing_jobs", type_="foreignkey"
    )
    op.drop_column("processing_jobs", "completed_at")
    op.drop_column("processing_jobs", "claim_expires_at")
    op.drop_column("processing_jobs", "claimed_at")
    op.drop_column("processing_jobs", "claim_token")
    op.drop_column("processing_jobs", "claimed_by")
    op.drop_column("processing_jobs", "correlation_id")
    op.drop_column("processing_jobs", "workspace_id")
