"""Add AI-COS workspace and authorization foundation.

Revision ID: 0029_ai_cos_access
Revises: 0028_mgmt_src_fresh
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_ai_cos_access"
down_revision: str | None = "0028_mgmt_src_fresh"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_workspace_slug"),
    )
    op.create_index("ix_workspace_status", "workspaces", ["status"])

    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("max_classification", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "actor_id", name="uq_workspace_membership_actor"
        ),
    )
    op.create_index(
        "ix_workspace_membership_role",
        "workspace_memberships",
        ["workspace_id", "role", "status"],
    )

    op.create_table(
        "permission_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("resource", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("effect", sa.String(length=10), nullable=False),
        sa.Column("max_classification", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "role",
            "resource",
            "action",
            "effect",
            "max_classification",
            name="uq_permission_policy_rule",
        ),
    )
    op.create_index(
        "ix_permission_policy_lookup",
        "permission_policies",
        ["workspace_id", "role", "resource", "action"],
    )

    op.create_table(
        "authorization_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("resource", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=160), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("classification", sa.String(length=30), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_authorization_workspace_created",
        "authorization_audits",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_authorization_actor_created",
        "authorization_audits",
        ["actor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_authorization_actor_created", table_name="authorization_audits")
    op.drop_index("ix_authorization_workspace_created", table_name="authorization_audits")
    op.drop_table("authorization_audits")
    op.drop_index("ix_permission_policy_lookup", table_name="permission_policies")
    op.drop_table("permission_policies")
    op.drop_index("ix_workspace_membership_role", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_index("ix_workspace_status", table_name="workspaces")
    op.drop_table("workspaces")
