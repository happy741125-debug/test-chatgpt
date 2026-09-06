"""Create LINE data foundation tables.

Revision ID: 0001_line_foundation
Revises:
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_line_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_status", sa.String(40), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("platform", "external_event_id", name="uq_raw_event_external"),
    )
    op.create_table(
        "channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_channel_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("channel_type", sa.String(40), nullable=False),
        sa.Column("company_id", sa.String(36), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("monitoring_level", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("silent_mode", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform", "external_channel_id", name="uq_channel_external"),
    )
    op.create_table(
        "people",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("company_id", sa.String(36), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("external_conversation_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "channel_id", "external_conversation_id", name="uq_conversation_external"
        ),
    )
    op.create_table(
        "identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_identity_id", sa.String(255), nullable=False),
        sa.Column("person_id", sa.String(36), sa.ForeignKey("people.id"), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform", "external_identity_id", name="uq_identity_external"),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_message_id", sa.String(255), nullable=False),
        sa.Column("raw_event_id", sa.String(36), sa.ForeignKey("raw_events.id"), nullable=False),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column(
            "sender_identity_id", sa.String(36), sa.ForeignKey("identities.id"), nullable=True
        ),
        sa.Column("message_type", sa.String(40), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_status", sa.String(40), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("platform", "external_message_id", name="uq_message_external"),
    )
    op.create_index("ix_messages_channel_created", "messages", ["channel_id", "source_created_at"])
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_jobs_status_available", "processing_jobs", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_status_available", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_index("ix_messages_channel_created", table_name="messages")
    op.drop_table("messages")
    op.drop_table("identities")
    op.drop_table("conversations")
    op.drop_table("people")
    op.drop_table("channels")
    op.drop_table("raw_events")
