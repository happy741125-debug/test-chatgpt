"""Create AI gateway audit tables.

Revision ID: 0003_ai_gateway
Revises: 0002_contexts
Create Date: 2026-09-07
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0003_ai_gateway"
down_revision: str | None = "0002_contexts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_PROMPT_ID = "00000000-0000-4000-8000-000000000003"


def upgrade() -> None:
    prompt_versions = op.create_table(
        "prompt_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("output_schema_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", "version", name="uq_prompt_version_name_version"),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        prompt_versions,
        [
            {
                "id": DEFAULT_PROMPT_ID,
                "name": "context-intelligence",
                "version": 1,
                "template_text": (
                    "Analyze the LINE conversation as Huoda operational intelligence. "
                    "Return only data matching output schema v1 and cite source message IDs."
                ),
                "output_schema_version": "v1",
                "status": "ACTIVE",
                "created_at": now,
                "activated_at": now,
            }
        ],
    )
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("context_id", sa.String(36), sa.ForeignKey("contexts.id"), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column(
            "prompt_version_id",
            sa.String(36),
            sa.ForeignKey("prompt_versions.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("raw_response_json", sa.JSON(), nullable=True),
        sa.Column("validated_output_json", sa.JSON(), nullable=True),
        sa.Column("overall_confidence", sa.Float(), nullable=True),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_microunits", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_runs_context_created", "ai_runs", ["context_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_runs_context_created", table_name="ai_runs")
    op.drop_table("ai_runs")
    op.drop_table("prompt_versions")
