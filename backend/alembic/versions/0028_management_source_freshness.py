"""Add per-source freshness policy to the operations master.

Revision ID: 0028_mgmt_src_fresh
Revises: 0027_ops_master_data
Create Date: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_mgmt_src_fresh"
down_revision: str | None = "0027_ops_master_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column("freshness_threshold_hours", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "freshness_threshold_hours")
