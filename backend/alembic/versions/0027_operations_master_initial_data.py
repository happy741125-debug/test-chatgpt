"""Add operations master source, batch, record, and audit tables.

Revision ID: 0027_operations_master_initial_data
Revises: 0026_work_calendar
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_operations_master_initial_data"
down_revision: str | None = "0026_work_calendar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_registry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("authority_scope", sa.Text(), nullable=False),
        sa.Column("sync_mode", sa.String(length=30), nullable=False),
        sa.Column("retention_policy", sa.String(length=80), nullable=False),
        sa.Column("contains_sensitive_data", sa.Boolean(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "management_import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("quality_status", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256"),
    )
    op.create_index(
        "ix_management_import_source_created",
        "management_import_batches",
        ["source_id", "created_at"],
    )
    op.create_table(
        "management_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("source_record_key", sa.String(length=160), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.String(length=50), nullable=True),
        sa.Column("subject_key", sa.String(length=160), nullable=True),
        sa.Column("fact_status", sa.String(length=40), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False),
        sa.Column("sensitivity", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("evidence_ref", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["management_import_batches.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "source_record_key", name="uq_management_source_record"
        ),
    )
    op.create_index(
        "ix_management_module_status",
        "management_records",
        ["module", "lifecycle_status"],
    )
    op.create_index(
        "ix_management_sensitivity_module",
        "management_records",
        ["sensitivity", "module"],
    )
    op.create_table(
        "management_record_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("actor_text", sa.String(length=120), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id"], ["management_records.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_management_audit_record_created",
        "management_record_audits",
        ["record_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_management_audit_record_created", table_name="management_record_audits"
    )
    op.drop_table("management_record_audits")
    op.drop_index(
        "ix_management_sensitivity_module", table_name="management_records"
    )
    op.drop_index("ix_management_module_status", table_name="management_records")
    op.drop_table("management_records")
    op.drop_index(
        "ix_management_import_source_created",
        table_name="management_import_batches",
    )
    op.drop_table("management_import_batches")
    op.drop_table("source_registry")
