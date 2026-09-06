"""Create Huoda domain taxonomy and intelligence tables.

Revision ID: 0004_domain_intelligence
Revises: 0003_ai_gateway
Create Date: 2026-09-07
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0004_domain_intelligence"
down_revision: str | None = "0003_ai_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOMAINS = (
    ("WAREHOUSE_OPERATIONS", "倉儲營運", "缺貨、叫貨、揀貨、出貨與庫存異常"),
    ("CUSTOMER", "客戶", "客訴、需求變更、服務異常與流失風險"),
    ("SALES", "業務", "新客戶、報價、提案、合約與成交進度"),
    ("FINANCE_COST", "財務與成本", "人事、耗材、物流與異常支出"),
    ("PEOPLE", "人員", "請假、缺工、加班、人力調度與訓練"),
    ("ALLIANCE_WAREHOUSE", "聯盟倉", "合作據點導入、異常與 SOP 落差"),
    ("SYSTEM", "系統", "WMS、訂單、API、權限與資料錯誤"),
    ("MANAGEMENT", "管理", "跨部門卡點、承諾、決策與追蹤"),
    ("UNKNOWN", "未知", "尚待人工確認的營運領域"),
)

EVENT_TYPES = (
    ("STOCK_SHORTAGE", "WAREHOUSE_OPERATIONS", "庫存短缺"),
    ("REPLENISHMENT", "WAREHOUSE_OPERATIONS", "叫貨／補貨"),
    ("OUTBOUND_DELAY", "WAREHOUSE_OPERATIONS", "出貨延誤"),
    ("CUSTOMER_COMPLAINT", "CUSTOMER", "客訴"),
    ("COST_ANOMALY", "FINANCE_COST", "成本異常"),
    ("STAFFING_GAP", "PEOPLE", "人力不足"),
    ("ALLIANCE_ISSUE", "ALLIANCE_WAREHOUSE", "聯盟倉異常"),
    ("SYSTEM_INCIDENT", "SYSTEM", "系統異常"),
    ("COMMERCIAL_PROGRESS", "SALES", "商務進度"),
    ("MANAGEMENT_DECISION", "MANAGEMENT", "管理決策"),
    ("UNKNOWN", "UNKNOWN", "未知事件"),
)


def upgrade() -> None:
    domains = op.create_table(
        "domains",
        sa.Column("code", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        domains,
        [
            {
                "code": code,
                "name": name,
                "description": description,
                "taxonomy_version": 1,
                "active": True,
                "created_at": now,
            }
            for code, name, description in DOMAINS
        ],
    )
    event_types = op.create_table(
        "event_types",
        sa.Column("code", sa.String(100), primary_key=True),
        sa.Column("domain_code", sa.String(80), sa.ForeignKey("domains.code"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.bulk_insert(
        event_types,
        [
            {
                "code": code,
                "domain_code": domain,
                "name": name,
                "description": name,
                "active": True,
                "created_at": now,
            }
            for code, domain, name in EVENT_TYPES
        ],
    )
    op.create_table(
        "aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("target_type", sa.String(60), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("alias_text", sa.String(255), nullable=False),
        sa.Column("normalized_text", sa.String(255), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("target_type", "target_id", "alias_text", name="uq_alias_target_text"),
    )
    op.create_table(
        "intelligence_objects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("context_id", sa.String(36), sa.ForeignKey("contexts.id"), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("ai_run_id", sa.String(36), sa.ForeignKey("ai_runs.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("domain_code", sa.String(80), sa.ForeignKey("domains.code"), nullable=False),
        sa.Column(
            "event_type_code",
            sa.String(100),
            sa.ForeignKey("event_types.code"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("owner_text", sa.String(255), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_raw_text", sa.String(255), nullable=True),
        sa.Column("requires_user_action", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("priority_score", sa.Integer(), nullable=False),
        sa.Column("priority_level", sa.String(10), nullable=False),
        sa.Column("priority_reasons_json", sa.JSON(), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "context_id",
            "context_version",
            "fingerprint",
            name="uq_intelligence_context_fingerprint",
        ),
    )
    op.create_index(
        "ix_intelligence_attention",
        "intelligence_objects",
        ["priority_level", "status", "deadline_at"],
    )
    op.create_index(
        "ix_intelligence_domain_created",
        "intelligence_objects",
        ["domain_code", "created_at"],
    )
    op.create_table(
        "intelligence_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "intelligence_id",
            sa.String(36),
            sa.ForeignKey("intelligence_objects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("context_id", sa.String(36), sa.ForeignKey("contexts.id"), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("evidence_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "intelligence_id",
            "message_id",
            name="uq_intelligence_source_message",
        ),
    )


def downgrade() -> None:
    op.drop_table("intelligence_sources")
    op.drop_index("ix_intelligence_domain_created", table_name="intelligence_objects")
    op.drop_index("ix_intelligence_attention", table_name="intelligence_objects")
    op.drop_table("intelligence_objects")
    op.drop_table("aliases")
    op.drop_table("event_types")
    op.drop_table("domains")
