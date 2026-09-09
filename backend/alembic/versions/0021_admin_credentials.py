"""Add admin credential table for in-app password change.

Revision ID: 0021_admin_credentials
Revises: 0020_v35_stage2
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_admin_credentials"
down_revision: str | None = "0020_v35_stage2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_credentials",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("admin_credentials")
