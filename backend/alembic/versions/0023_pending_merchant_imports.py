"""Add pending merchant import requests.

Revision ID: 0023_pending_merchant_imports
Revises: 0022_upload_data_governance
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_pending_merchant_imports"
down_revision: str | None = "0022_upload_data_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gowarehouse_pending_imports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("requested_merchant_name", sa.String(length=120), nullable=False),
        sa.Column("merchant_id", sa.String(length=36), nullable=False),
        sa.Column("warehouse_id", sa.String(length=36), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchant_masters.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouse_masters.id"]),
        sa.ForeignKeyConstraint(["import_batch_id"], ["gowarehouse_import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256"),
    )
    op.create_index(
        "ix_gw_pending_merchant_status",
        "gowarehouse_pending_imports",
        ["merchant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_gw_pending_merchant_status", table_name="gowarehouse_pending_imports")
    op.drop_table("gowarehouse_pending_imports")
