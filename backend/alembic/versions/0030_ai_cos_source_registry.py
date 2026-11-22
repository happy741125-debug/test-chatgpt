"""Extend source registry for cross-workspace AI-COS sources.

Revision ID: 0030_ai_cos_sources
Revises: 0029_ai_cos_access
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_ai_cos_sources"
down_revision: str | None = "0029_ai_cos_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_registry", sa.Column("workspace_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "source_registry",
        sa.Column("external_source_key", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "authorization_status",
            sa.String(length=30),
            server_default="LEGACY",
            nullable=False,
        ),
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "authorized_scopes_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.add_column(
        "source_registry", sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "source_registry", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "source_registry", sa.Column("revocation_reason", sa.Text(), nullable=True)
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "classification",
            sa.String(length=30),
            server_default="INTERNAL",
            nullable=False,
        ),
    )
    op.add_column(
        "source_registry", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "source_registry", sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "source_registry", sa.Column("cursor_ref", sa.String(length=255), nullable=True)
    )
    op.create_foreign_key(
        "fk_source_registry_workspace",
        "source_registry",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_source_workspace_external",
        "source_registry",
        ["workspace_id", "source_type", "external_source_key"],
    )
    op.create_index(
        "ix_source_workspace_status",
        "source_registry",
        ["workspace_id", "authorization_status"],
    )
    op.alter_column("source_registry", "authorization_status", server_default=None)
    op.alter_column("source_registry", "authorized_scopes_json", server_default=None)
    op.alter_column("source_registry", "classification", server_default=None)

    op.create_table(
        "source_authorization_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("before_status", sa.String(length=30), nullable=True),
        sa.Column("after_status", sa.String(length=30), nullable=False),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source_registry.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_auth_audit_source_created",
        "source_authorization_audits",
        ["source_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_auth_audit_source_created",
        table_name="source_authorization_audits",
    )
    op.drop_table("source_authorization_audits")
    op.drop_index("ix_source_workspace_status", table_name="source_registry")
    op.drop_constraint(
        "uq_source_workspace_external", "source_registry", type_="unique"
    )
    op.drop_constraint(
        "fk_source_registry_workspace", "source_registry", type_="foreignkey"
    )
    for column in (
        "cursor_ref",
        "last_error_at",
        "last_success_at",
        "classification",
        "revocation_reason",
        "revoked_at",
        "authorized_at",
        "authorized_scopes_json",
        "authorization_status",
        "external_source_key",
        "workspace_id",
    ):
        op.drop_column("source_registry", column)
