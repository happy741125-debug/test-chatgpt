from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ManagementSource,
    SourceRecord,
    SourceRecordAudit,
    SourceRecordEvidence,
    utc_now,
)
from app.security.authorization import CLASSIFICATION_RANK

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RETENTION_DAYS = {"30_DAYS": 30, "90_DAYS": 90, "365_DAYS": 365}


@dataclass(frozen=True)
class SourceRecordResult:
    record: SourceRecord
    created: bool


def ingest_source_record(
    session: Session,
    *,
    workspace_id: str,
    source_id: str,
    external_record_key: str,
    record_type: str,
    content_ref: str,
    content_sha256: str,
    classification: str,
    actor_id: str,
    mime_type: str | None = None,
    source_created_at: datetime | None = None,
    received_at: datetime | None = None,
    canonical_hash: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, object] | None = None,
    evidence_ref: str | None = None,
) -> SourceRecordResult:
    source = session.get(ManagementSource, source_id)
    if source is None:
        raise ValueError("SOURCE_NOT_FOUND")
    if source.workspace_id != workspace_id:
        raise ValueError("CROSS_WORKSPACE_SOURCE_DENIED")
    if source.authorization_status != "ACTIVE":
        raise ValueError("SOURCE_NOT_AUTHORIZED")
    if classification not in CLASSIFICATION_RANK:
        raise ValueError("CLASSIFICATION_UNKNOWN")
    if CLASSIFICATION_RANK[classification] < CLASSIFICATION_RANK[source.classification]:
        raise ValueError("CLASSIFICATION_DOWNGRADE_DENIED")

    external_key = external_record_key.strip()
    normalized_type = record_type.strip().upper()
    normalized_ref = content_ref.strip()
    content_hash = content_sha256.strip().lower()
    canonical = (canonical_hash or content_hash).strip().lower()
    if not external_key:
        raise ValueError("EXTERNAL_RECORD_KEY_REQUIRED")
    if not normalized_type:
        raise ValueError("RECORD_TYPE_REQUIRED")
    if not normalized_ref:
        raise ValueError("CONTENT_REF_REQUIRED")
    if not SHA256_PATTERN.fullmatch(content_hash):
        raise ValueError("CONTENT_SHA256_INVALID")
    if not SHA256_PATTERN.fullmatch(canonical):
        raise ValueError("CANONICAL_HASH_INVALID")

    existing = session.scalar(
        select(SourceRecord).where(
            SourceRecord.source_id == source_id,
            SourceRecord.external_record_key == external_key,
        )
    )
    if existing is not None:
        if existing.canonical_hash != canonical:
            raise ValueError("SOURCE_RECORD_CONFLICT")
        return SourceRecordResult(record=existing, created=False)

    received = received_at or utc_now()
    stable_idempotency = idempotency_key or hashlib.sha256(
        f"{source_id}:{external_key}:{canonical}".encode()
    ).hexdigest()
    retention_days = RETENTION_DAYS.get(source.retention_policy)
    authorization_version = (
        source.authorized_at.isoformat() if source.authorized_at is not None else "ACTIVE"
    )
    record = SourceRecord(
        workspace_id=workspace_id,
        source_id=source_id,
        external_record_key=external_key,
        record_type=normalized_type,
        content_ref=normalized_ref,
        content_sha256=content_hash,
        canonical_hash=canonical,
        mime_type=mime_type,
        source_created_at=source_created_at,
        received_at=received,
        classification=classification,
        authorization_version=authorization_version,
        retention_until=(
            received + timedelta(days=retention_days) if retention_days is not None else None
        ),
        processing_status="RECEIVED",
        normalized_version=1,
        idempotency_key=stable_idempotency,
        metadata_json=metadata or {},
    )
    session.add(record)
    session.flush()
    session.add(
        SourceRecordEvidence(
            source_record_id=record.id,
            evidence_type="CONTENT_REFERENCE",
            evidence_ref=evidence_ref or normalized_ref,
            content_sha256=content_hash,
            metadata_json={},
        )
    )
    _audit(
        session,
        record=record,
        actor_id=actor_id,
        event_type="INGESTED",
        before_status=None,
        after_status="RECEIVED",
    )
    return SourceRecordResult(record=record, created=True)


def tombstone_source_record(
    session: Session,
    *,
    workspace_id: str,
    source_record_id: str,
    actor_id: str,
    reason: str,
    now: datetime | None = None,
) -> SourceRecord:
    record = session.get(SourceRecord, source_record_id)
    if record is None:
        raise ValueError("SOURCE_RECORD_NOT_FOUND")
    if record.workspace_id != workspace_id:
        raise ValueError("CROSS_WORKSPACE_RECORD_DENIED")
    if not reason.strip():
        raise ValueError("TOMBSTONE_REASON_REQUIRED")
    before = record.processing_status
    record.processing_status = "TOMBSTONED"
    record.tombstoned_at = now or utc_now()
    _audit(
        session,
        record=record,
        actor_id=actor_id,
        event_type="TOMBSTONED",
        before_status=before,
        after_status="TOMBSTONED",
        reason=reason.strip(),
    )
    return record


def _audit(
    session: Session,
    *,
    record: SourceRecord,
    actor_id: str,
    event_type: str,
    before_status: str | None,
    after_status: str,
    reason: str | None = None,
) -> None:
    session.add(
        SourceRecordAudit(
            source_record_id=record.id,
            workspace_id=record.workspace_id,
            actor_id=actor_id,
            event_type=event_type,
            before_status=before_status,
            after_status=after_status,
            reason=reason,
        )
    )
