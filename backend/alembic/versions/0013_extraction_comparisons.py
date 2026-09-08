"""Add shadow-mode extraction comparison records.

Revision ID: 0013_extraction_comparisons
Revises: 0012_cross_source_operations
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_extraction_comparisons"
down_revision: str | None = "0012_cross_source_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extraction_comparisons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("primary_provider", sa.String(length=80), nullable=False),
        sa.Column("primary_model", sa.String(length=120), nullable=False),
        sa.Column("primary_output_json", sa.JSON(), nullable=False),
        sa.Column("shadow_provider", sa.String(length=80), nullable=False),
        sa.Column("shadow_model", sa.String(length=120), nullable=False),
        sa.Column("shadow_status", sa.String(length=20), nullable=False),
        sa.Column("shadow_error_code", sa.String(length=100), nullable=True),
        sa.Column("shadow_output_json", sa.JSON(), nullable=True),
        sa.Column("shadow_latency_ms", sa.Integer(), nullable=True),
        sa.Column("shadow_cost_microunits", sa.Integer(), nullable=True),
        sa.Column("agreement", sa.String(length=20), nullable=False),
        sa.Column("diff_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["context_id"], ["contexts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "context_id", "context_version", name="uq_extraction_comparison_context"
        ),
    )
    op.create_index(
        "ix_extraction_comparison_created",
        "extraction_comparisons",
        ["agreement", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_comparison_created", table_name="extraction_comparisons")
    op.drop_table("extraction_comparisons")
