"""Add Gmail source connections and thread-aware contexts.

Revision ID: 0006_gmail_foundation
Revises: 0005_urgent_order_event
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_gmail_foundation"
down_revision: str | None = "0005_urgent_order_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_account_id", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "platform",
            "external_account_id",
            name="uq_source_connection_account",
        ),
    )
    op.create_table(
        "source_oauth_states",
        sa.Column("state", sa.String(160), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "source_sync_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("source_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("history_id", sa.String(255), nullable=True),
        sa.Column("initial_sync_completed", sa.Boolean(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", name="uq_source_sync_connection"),
    )
    with op.batch_alter_table("contexts") as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_contexts_conversation_id",
            "conversations",
            ["conversation_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("contexts") as batch_op:
        batch_op.drop_constraint("fk_contexts_conversation_id", type_="foreignkey")
        batch_op.drop_column("conversation_id")
    op.drop_table("source_sync_states")
    op.drop_table("source_oauth_states")
    op.drop_table("source_connections")
