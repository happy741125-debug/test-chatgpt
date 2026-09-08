"""Add audience routing and intelligence status audit trail.

Revision ID: 0014_attention_status_audit
Revises: 0013_extraction_comparisons
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_attention_status_audit"
down_revision: str | None = "0013_extraction_comparisons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    event_types = sa.table(
        "event_types",
        sa.column("code", sa.String),
        sa.column("domain_code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    taxonomy = (
        ("INBOUND_OPERATION", "WAREHOUSE_OPERATIONS", "進倉／入庫作業"),
        ("DISPATCH_REQUEST", "WAREHOUSE_OPERATIONS", "出貨／派件需求"),
        ("SHIPMENT_DISCREPANCY", "CUSTOMER", "出貨內容落差"),
        ("RETURN_EXCHANGE", "CUSTOMER", "退貨／換貨需求"),
        ("SYSTEM_ONBOARDING", "SYSTEM", "系統設定／串接"),
        ("QUOTE_REQUEST", "SALES", "報價需求"),
        ("CONTRACT_PROGRESS", "SALES", "合約進度"),
        ("OPERATIONAL_ANNOUNCEMENT", "MANAGEMENT", "營運公告／作業異動"),
    )
    bind = op.get_bind()
    for code, domain_code, name in taxonomy:
        exists = bind.execute(
            sa.text("SELECT code FROM event_types WHERE code = :code"), {"code": code}
        ).first()
        if exists is None:
            bind.execute(
                event_types.insert().values(
                    code=code,
                    domain_code=domain_code,
                    name=name,
                    description=name,
                    active=True,
                    created_at=sa.func.now(),
                )
            )

    op.add_column(
        "intelligence_objects",
        sa.Column("attention_level", sa.String(length=10), nullable=False, server_default="TEAM"),
    )
    op.add_column(
        "intelligence_objects",
        sa.Column("attention_reasons_json", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "intelligence_status_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=False),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("actor_text", sa.String(length=120), nullable=False),
        sa.Column("evidence_message_ids_json", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["intelligence_id"], ["intelligence_objects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intelligence_status_audit_card_created",
        "intelligence_status_audits",
        ["intelligence_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_status_audit_card_created",
        table_name="intelligence_status_audits",
    )
    op.drop_table("intelligence_status_audits")
    op.drop_column("intelligence_objects", "attention_reasons_json")
    op.drop_column("intelligence_objects", "attention_level")
