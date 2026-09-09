from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Platform(StrEnum):
    LINE = "LINE"
    GMAIL = "GMAIL"


class SourceConnectionStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    DISCONNECTED = "DISCONNECTED"


class ProcessingStatus(StrEnum):
    RECEIVED = "RECEIVED"
    NORMALIZED = "NORMALIZED"
    QUEUED = "QUEUED"
    CONTEXT_PENDING = "CONTEXT_PENDING"
    ANALYZING = "ANALYZING"
    PROCESSED = "PROCESSED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    UNSUPPORTED = "UNSUPPORTED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    PROCESSED = "PROCESSED"
    DEAD_LETTER = "DEAD_LETTER"


class ContextStatus(StrEnum):
    OPEN = "OPEN"
    READY = "READY"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    FAILED = "FAILED"


class PromptStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class AIRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class IntelligenceStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    LIKELY_DONE = "LIKELY_DONE"
    DONE = "DONE"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class AttentionLevel(StrEnum):
    BOSS = "BOSS"
    TEAM = "TEAM"
    NOISE = "NOISE"


class ComparisonAgreement(StrEnum):
    AGREE = "AGREE"
    PARTIAL = "PARTIAL"
    DISAGREE = "DISAGREE"
    SHADOW_FAILED = "SHADOW_FAILED"


class Base(DeclarativeBase):
    pass


class SourceConnection(Base):
    __tablename__ = "source_connections"
    __table_args__ = (
        UniqueConstraint("platform", "external_account_id", name="uq_source_connection_account"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(20))
    external_account_id: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=SourceConnectionStatus.PENDING.value)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SourceOAuthState(Base):
    __tablename__ = "source_oauth_states"

    state: Mapped[str] = mapped_column(String(160), primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceSyncState(Base):
    __tablename__ = "source_sync_states"
    __table_args__ = (UniqueConstraint("connection_id", name="uq_source_sync_connection"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("source_connections.id", ondelete="CASCADE")
    )
    history_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    initial_sync_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ExecutiveMetricSnapshot(Base):
    __tablename__ = "executive_metric_snapshots"

    metric_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    health_status: Mapped[str] = mapped_column(String(20), default="NO_DATA")
    period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AdminCredential(Base):
    """Single-row admin password. When set, its hash is an accepted login in
    addition to the env OPS_API_TOKEN (which stays as break-glass recovery)."""

    __tablename__ = "admin_credentials"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="singleton")
    password_hash: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"
    __table_args__ = (UniqueConstraint("week_end", name="uq_weekly_review_week_end"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    manager_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ImprovementAction(Base):
    __tablename__ = "improvement_actions"
    __table_args__ = (Index("ix_improvement_action_status_due", "status", "due_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_id: Mapped[str] = mapped_column(ForeignKey("weekly_reviews.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    issue_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_name: Mapped[str] = mapped_column(String(120))
    target_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    needs_jacky: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RevenueImportBatch(Base):
    __tablename__ = "revenue_import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    period_count: Mapped[int] = mapped_column(Integer)
    record_count: Mapped[int] = mapped_column(Integer)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RevenueRecord(Base):
    __tablename__ = "revenue_records"
    __table_args__ = (
        UniqueConstraint(
            "period",
            "warehouse",
            "source_customer_label",
            name="uq_revenue_period_warehouse_customer",
        ),
        Index("ix_revenue_period", "period"),
        Index("ix_revenue_customer_period", "customer_code", "period"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    import_batch_id: Mapped[str] = mapped_column(
        ForeignKey("revenue_import_batches.id", ondelete="CASCADE")
    )
    period: Mapped[str] = mapped_column(String(7))
    warehouse: Mapped[str] = mapped_column(String(40))
    customer_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255))
    source_customer_label: Mapped[str] = mapped_column(String(255))
    warehouse_rent: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    handling_system: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    processing: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    logistics: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    other: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RevenueDataIssue(Base):
    __tablename__ = "revenue_data_issues"
    __table_args__ = (Index("ix_revenue_issue_period", "period", "severity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    import_batch_id: Mapped[str] = mapped_column(
        ForeignKey("revenue_import_batches.id", ondelete="CASCADE")
    )
    period: Mapped[str] = mapped_column(String(7))
    severity: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(80))
    cell_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    source_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    calculated_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    difference: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalImportBatch(Base):
    __tablename__ = "operational_import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    record_count: Mapped[int] = mapped_column(Integer)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalOrderRecord(Base):
    __tablename__ = "operational_order_records"
    __table_args__ = (
        Index("ix_operational_order_date", "order_date"),
        Index("ix_operational_warehouse_date", "warehouse", "order_date"),
    )

    order_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        ForeignKey("operational_import_batches.id", ondelete="CASCADE")
    )
    order_date: Mapped[date] = mapped_column(Date)
    warehouse: Mapped[str] = mapped_column(String(80))
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="OPEN")
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    exception_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worker_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class GoWarehouseImportBatch(Base):
    __tablename__ = "gowarehouse_import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))  # "orders" | "inventory"
    merchant: Mapped[str | None] = mapped_column(String(120), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GoWarehouseOrder(Base):
    __tablename__ = "gowarehouse_orders"
    __table_args__ = (Index("ix_gw_order_merchant", "merchant"),)

    # id = "<merchant>::<order_id>" so re-imports upsert instead of duplicating.
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        ForeignKey("gowarehouse_import_batches.id", ondelete="CASCADE")
    )
    merchant: Mapped[str] = mapped_column(String(120))
    order_id: Mapped[str] = mapped_column(String(120))
    channel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shipping_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    reserved_ship_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GoWarehouseInventory(Base):
    __tablename__ = "gowarehouse_inventory"
    __table_args__ = (Index("ix_gw_inventory_merchant", "merchant"),)

    # id = hash(merchant|sku|batch|inventory_type) so re-imports upsert.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        ForeignKey("gowarehouse_import_batches.id", ondelete="CASCADE")
    )
    merchant: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str] = mapped_column(String(120))
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inventory_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    batch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allocated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GoWarehouseOperationalRecord(Base):
    __tablename__ = "gowarehouse_operational_records"
    __table_args__ = (
        Index("ix_gw_operational_kind_date", "kind", "occurred_on"),
        Index("ix_gw_operational_warehouse", "warehouse"),
    )

    # Source identifiers are hashed before persistence; PII columns are never imported.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        ForeignKey("gowarehouse_import_batches.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(24))
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    warehouse: Mapped[str | None] = mapped_column(String(120), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    planned_quantity: Mapped[int] = mapped_column(Integer, default=0)
    accepted_quantity: Mapped[int] = mapped_column(Integer, default=0)
    completed_quantity: Mapped[int] = mapped_column(Integer, default=0)
    shipment_count: Mapped[int] = mapped_column(Integer, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WeeklyOperationsInput(Base):
    __tablename__ = "weekly_operations_inputs"
    __table_args__ = (
        UniqueConstraint("week_start", "warehouse", name="uq_weekly_operations_week_warehouse"),
        Index("ix_weekly_operations_week", "week_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    week_start: Mapped[date] = mapped_column(Date)
    warehouse: Mapped[str] = mapped_column(String(80))
    labor_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consumables_inventory_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    inventory_count_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inventory_variance_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pallet_placement_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RawEvent(Base):
    __tablename__ = "raw_events"
    __table_args__ = (
        UniqueConstraint("platform", "external_event_id", name="uq_raw_event_external"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(20), default=Platform.LINE.value)
    external_event_id: Mapped[str] = mapped_column(String(255))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processing_status: Mapped[str] = mapped_column(
        String(40), default=ProcessingStatus.RECEIVED.value
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("platform", "external_channel_id", name="uq_channel_external"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(20), default=Platform.LINE.value)
    external_channel_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel_type: Mapped[str] = mapped_column(String(40))
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    monitoring_level: Mapped[str] = mapped_column(String(20), default="B")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    silent_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("channel_id", "external_conversation_id", name="uq_conversation_external"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    external_conversation_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Person(Base):
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(255))
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Identity(Base):
    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("platform", "external_identity_id", name="uq_identity_external"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(20), default=Platform.LINE.value)
    external_identity_id: Mapped[str] = mapped_column(String(255))
    person_id: Mapped[str | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("platform", "external_message_id", name="uq_message_external"),
        Index("ix_messages_channel_created", "channel_id", "source_created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(20), default=Platform.LINE.value)
    external_message_id: Mapped[str] = mapped_column(String(255))
    raw_event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"))
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    sender_identity_id: Mapped[str | None] = mapped_column(
        ForeignKey("identities.id"), nullable=True
    )
    message_type: Mapped[str] = mapped_column(String(40))
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processing_status: Mapped[str] = mapped_column(
        String(40), default=ProcessingStatus.QUEUED.value
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "external_attachment_id", name="uq_attachment_message_external"
        ),
        Index("ix_attachments_status_created", "processing_status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(20))
    external_attachment_id: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(30), default="METADATA_ONLY")
    sensitive_level: Mapped[str] = mapped_column(String(20), default="RESTRICTED")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retention_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AttachmentAccessAudit(Base):
    __tablename__ = "attachment_access_audits"
    __table_args__ = (Index("ix_attachment_access_created", "attachment_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attachment_id: Mapped[str] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE")
    )
    actor_text: Mapped[str] = mapped_column(String(120), default="OPS_USER")
    action: Mapped[str] = mapped_column(String(40), default="VIEW_METADATA")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Context(Base):
    __tablename__ = "contexts"
    __table_args__ = (Index("ix_contexts_channel_status_end", "channel_id", "status", "end_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default=ContextStatus.OPEN.value)
    version: Mapped[int] = mapped_column(Integer, default=1)
    topic_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    urgent_bypass: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ContextMessage(Base):
    __tablename__ = "context_messages"
    __table_args__ = (
        UniqueConstraint("context_id", "sequence", name="uq_context_message_sequence"),
        UniqueConstraint("message_id", name="uq_context_message_once"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    context_id: Mapped[str] = mapped_column(ForeignKey("contexts.id", ondelete="CASCADE"))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    included_reason: Mapped[str] = mapped_column(String(80), default="TIME_WINDOW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_version_name_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    template_text: Mapped[str] = mapped_column(Text)
    output_schema_version: Mapped[str] = mapped_column(String(40), default="v1")
    status: Mapped[str] = mapped_column(String(20), default=PromptStatus.DRAFT.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (Index("ix_ai_runs_context_created", "context_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    context_id: Mapped[str] = mapped_column(ForeignKey("contexts.id"))
    context_version: Mapped[int] = mapped_column(Integer)
    prompt_version_id: Mapped[str] = mapped_column(ForeignKey("prompt_versions.id"))
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default=AIRunStatus.RUNNING.value)
    raw_response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validated_output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_microunits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Domain(Base):
    __tablename__ = "domains"

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    taxonomy_version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EventType(Base):
    __tablename__ = "event_types"

    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    domain_code: Mapped[str] = mapped_column(ForeignKey("domains.code"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Alias(Base):
    __tablename__ = "aliases"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "alias_text", name="uq_alias_target_text"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str] = mapped_column(String(100))
    alias_text: Mapped[str] = mapped_column(String(255))
    normalized_text: Mapped[str] = mapped_column(String(255))
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntelligenceObject(Base):
    __tablename__ = "intelligence_objects"
    __table_args__ = (
        UniqueConstraint(
            "context_id",
            "context_version",
            "fingerprint",
            name="uq_intelligence_context_fingerprint",
        ),
        Index("ix_intelligence_attention", "priority_level", "status", "deadline_at"),
        Index("ix_intelligence_domain_created", "domain_code", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    facets_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_id: Mapped[str] = mapped_column(ForeignKey("contexts.id"))
    context_version: Mapped[int] = mapped_column(Integer)
    ai_run_id: Mapped[str] = mapped_column(ForeignKey("ai_runs.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(40))
    domain_code: Mapped[str] = mapped_column(ForeignKey("domains.code"))
    event_type_code: Mapped[str] = mapped_column(ForeignKey("event_types.code"))
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default=IntelligenceStatus.OPEN.value)
    owner_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_raw_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requires_user_action: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float)
    priority_score: Mapped[int] = mapped_column(Integer, default=0)
    priority_level: Mapped[str] = mapped_column(String(10), default="P3")
    priority_reasons_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    attention_level: Mapped[str] = mapped_column(String(10), default=AttentionLevel.TEAM.value)
    attention_reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    attention_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    lifecycle_stage: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    blocker_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    change_kind: Mapped[str] = mapped_column(String(30), default="NEW")
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class IntelligenceSource(Base):
    __tablename__ = "intelligence_sources"
    __table_args__ = (
        UniqueConstraint("intelligence_id", "message_id", name="uq_intelligence_source_message"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intelligence_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_objects.id", ondelete="CASCADE")
    )
    context_id: Mapped[str] = mapped_column(ForeignKey("contexts.id"))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    evidence_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntelligenceStatusAudit(Base):
    __tablename__ = "intelligence_status_audits"
    __table_args__ = (
        Index("ix_intelligence_status_audit_card_created", "intelligence_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intelligence_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_objects.id", ondelete="CASCADE")
    )
    from_status: Mapped[str] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40))
    actor_text: Mapped[str] = mapped_column(String(120))
    evidence_message_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntelligenceFeedback(Base):
    __tablename__ = "intelligence_feedback"
    __table_args__ = (
        Index("ix_intelligence_feedback_card_created", "intelligence_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intelligence_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_objects.id", ondelete="CASCADE")
    )
    field_name: Mapped[str] = mapped_column(String(60))
    previous_value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    corrected_value_json: Mapped[Any] = mapped_column(JSON)
    actor_text: Mapped[str] = mapped_column(String(120), default="OPS_USER")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntelligenceChangeAudit(Base):
    __tablename__ = "intelligence_change_audits"
    __table_args__ = (
        Index("ix_intelligence_change_card_created", "intelligence_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intelligence_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_objects.id", ondelete="CASCADE")
    )
    change_kind: Mapped[str] = mapped_column(String(30))
    previous_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    blocker_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    evidence_message_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntelligenceHistoryEvent(Base):
    """Append-only lifecycle event. Once written it is never updated or deleted,
    so historical weekly statistics stay stable even as a case keeps changing."""

    __tablename__ = "intelligence_history_events"
    __table_args__ = (
        Index("ix_intelligence_history_occurred", "occurred_at"),
        Index("ix_intelligence_history_type_occurred", "event_type", "occurred_at"),
        Index("ix_intelligence_history_card_occurred", "intelligence_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intelligence_id: Mapped[str] = mapped_column(String(36), ForeignKey("intelligence_objects.id"))
    event_type: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_text: Mapped[str] = mapped_column(String(120), default="SYSTEM")
    evidence_message_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WeeklyReviewSnapshot(Base):
    """Frozen weekly statistics captured when a review is CLOSED, so a settled
    week never changes even if its cases are later updated or reopened."""

    __tablename__ = "weekly_review_snapshots"
    __table_args__ = (Index("ix_weekly_review_snapshot_week", "week_end", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    week_end: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    change_counts_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    change_event_ids_json: Mapped[dict[str, list[str]]] = mapped_column(JSON, default=dict)
    total_intelligence: Mapped[int] = mapped_column(Integer, default=0)
    urgent_intelligence: Mapped[int] = mapped_column(Integer, default=0)
    decisions_needed: Mapped[int] = mapped_column(Integer, default=0)
    metric_signals_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    actor_text: Mapped[str] = mapped_column(String(120), default="OPS_USER")


class CaseReviewItem(Base):
    __tablename__ = "case_review_items"
    __table_args__ = (
        UniqueConstraint(
            "intelligence_id", "candidate_intelligence_id", name="uq_case_review_pair"
        ),
        Index("ix_case_review_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intelligence_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_objects.id", ondelete="CASCADE")
    )
    candidate_intelligence_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_objects.id", ondelete="CASCADE")
    )
    score: Mapped[float] = mapped_column(Float)
    reasons_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    resolution: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseMergeAudit(Base):
    __tablename__ = "case_merge_audits"
    __table_args__ = (
        Index("ix_case_merge_target_created", "target_intelligence_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_intelligence_id: Mapped[str | None] = mapped_column(
        ForeignKey("intelligence_objects.id", ondelete="SET NULL"), nullable=True
    )
    target_intelligence_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_objects.id", ondelete="CASCADE")
    )
    source_context_id: Mapped[str | None] = mapped_column(
        ForeignKey("contexts.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(30))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    moved_message_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor_text: Mapped[str] = mapped_column(String(120), default="SYSTEM")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExtractionComparison(Base):
    """Shadow-mode record: what the rule-based primary produced vs the LLM.

    The LLM output is never materialised into cards; it lives here only so the
    two extractors can be compared before deciding whether to trust the LLM.
    """

    __tablename__ = "extraction_comparisons"
    __table_args__ = (
        UniqueConstraint(
            "context_id", "context_version", name="uq_extraction_comparison_context"
        ),
        Index("ix_extraction_comparison_created", "agreement", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    context_id: Mapped[str] = mapped_column(ForeignKey("contexts.id"))
    context_version: Mapped[int] = mapped_column(Integer)
    primary_provider: Mapped[str] = mapped_column(String(80))
    primary_model: Mapped[str] = mapped_column(String(120))
    primary_output_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    shadow_provider: Mapped[str] = mapped_column(String(80))
    shadow_model: Mapped[str] = mapped_column(String(120))
    shadow_status: Mapped[str] = mapped_column(String(20))
    shadow_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shadow_output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    shadow_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shadow_cost_microunits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agreement: Mapped[str] = mapped_column(String(20))
    diff_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (Index("ix_jobs_status_available", "status", "available_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_type: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40), default=JobStatus.QUEUED.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
