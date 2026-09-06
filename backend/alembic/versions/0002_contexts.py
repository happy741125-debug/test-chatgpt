"""Create conversation context tables.

Revision ID: 0002_contexts
Revises: 0001_line_foundation
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_contexts"
down_revision: str | None = "0001_line_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contexts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("topic_hint", sa.String(255), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("urgent_bypass", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_contexts_channel_status_end",
        "contexts",
        ["channel_id", "status", "end_at"],
    )
    op.create_table(
        "context_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "context_id",
            sa.String(36),
            sa.ForeignKey("contexts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("included_reason", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("context_id", "sequence", name="uq_context_message_sequence"),
        sa.UniqueConstraint("message_id", name="uq_context_message_once"),
    )


def downgrade() -> None:
    op.drop_table("context_messages")
    op.drop_index("ix_contexts_channel_status_end", table_name="contexts")
    op.drop_table("contexts")
