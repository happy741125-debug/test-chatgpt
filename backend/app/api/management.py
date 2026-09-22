from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import (
    ManagementImportBatch,
    ManagementRecord,
    ManagementRecordAudit,
    ManagementSource,
)

router = APIRouter(prefix="/api/v1/management", tags=["operations-master"])

ManagementModule = Literal["CAPACITY", "ISSUE", "SOP", "KPI", "ONBOARDING", "PEOPLE"]
FactStatus = Literal[
    "CONFIRMED",
    "USER_REPORTED",
    "CALCULATED_ESTIMATE",
    "PENDING_VERIFICATION",
    "PROPOSAL",
    "SENSITIVE_OBSERVATION",
]
LifecycleStatus = Literal["ACTIVE", "HISTORICAL", "RESOLVED", "SUPERSEDED"]
Sensitivity = Literal["INTERNAL", "PRIVATE_MANAGEMENT"]

MODULES: tuple[ManagementModule, ...] = (
    "CAPACITY",
    "ISSUE",
    "SOP",
    "KPI",
    "ONBOARDING",
    "PEOPLE",
)
FACT_STATUSES: tuple[FactStatus, ...] = (
    "CONFIRMED",
    "USER_REPORTED",
    "CALCULATED_ESTIMATE",
    "PENDING_VERIFICATION",
    "PROPOSAL",
    "SENSITIVE_OBSERVATION",
)
PENDING_FACT_STATUSES = {"PENDING_VERIFICATION", "PROPOSAL", "SENSITIVE_OBSERVATION"}


class ManagementRecordInput(BaseModel):
    source_record_key: str = Field(min_length=1, max_length=160)
    module: ManagementModule
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=5000)
    subject_type: str | None = Field(default=None, max_length=50)
    subject_key: str | None = Field(default=None, max_length=160)
    fact_status: FactStatus = "PENDING_VERIFICATION"
    lifecycle_status: LifecycleStatus = "ACTIVE"
    sensitivity: Sensitivity = "INTERNAL"
    observed_at: datetime | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    evidence_ref: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class ManagementImportRequest(BaseModel):
    source_code: str = Field(pattern=r"^[A-Z0-9_-]+$", min_length=2, max_length=80)
    source_name: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=40)
    authority_scope: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_version: int = Field(default=1, ge=1)
    records: list[ManagementRecordInput] = Field(min_length=1, max_length=500)


class ManagementImportResult(BaseModel):
    batch_id: str
    duplicate: bool
    created: int
    updated: int
    unchanged: int
    total_records: int


class ManagementRecordResponse(BaseModel):
    id: str
    module: str
    title: str
    summary: str
    subject_type: str | None
    subject_key: str | None
    fact_status: str
    lifecycle_status: str
    sensitivity: str
    observed_at: datetime | None
    effective_from: date | None
    effective_to: date | None
    evidence_ref: str | None
    payload: dict[str, Any]
    source_name: str
    source_version: int
    updated_at: datetime


class ManagementOverview(BaseModel):
    total_records: int
    private_records: int
    pending_confirmation: int
    by_module: dict[str, int]
    by_fact_status: dict[str, int]
    latest_update: datetime | None
    sources: int


def _record_snapshot(record: ManagementRecord) -> dict[str, Any]:
    return {
        "source_record_key": record.source_record_key,
        "source_version": record.source_version,
        "module": record.module,
        "title": record.title,
        "summary": record.summary,
        "subject_type": record.subject_type,
        "subject_key": record.subject_key,
        "fact_status": record.fact_status,
        "lifecycle_status": record.lifecycle_status,
        "sensitivity": record.sensitivity,
        "observed_at": record.observed_at.isoformat() if record.observed_at else None,
        "effective_from": record.effective_from.isoformat() if record.effective_from else None,
        "effective_to": record.effective_to.isoformat() if record.effective_to else None,
        "evidence_ref": record.evidence_ref,
        "payload": record.payload_json,
    }


def _incoming_snapshot(item: ManagementRecordInput, source_version: int) -> dict[str, Any]:
    snapshot = item.model_dump(mode="json")
    snapshot["source_version"] = source_version
    if item.module == "PEOPLE":
        snapshot["sensitivity"] = "PRIVATE_MANAGEMENT"
    return snapshot


def _response(record: ManagementRecord, source_name: str) -> ManagementRecordResponse:
    return ManagementRecordResponse(
        id=record.id,
        module=record.module,
        title=record.title,
        summary=record.summary,
        subject_type=record.subject_type,
        subject_key=record.subject_key,
        fact_status=record.fact_status,
        lifecycle_status=record.lifecycle_status,
        sensitivity=record.sensitivity,
        observed_at=record.observed_at,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        evidence_ref=record.evidence_ref,
        payload=record.payload_json,
        source_name=source_name,
        source_version=record.source_version,
        updated_at=record.updated_at,
    )


@router.get("/overview")
def get_management_overview(
    _: OpsAccess,
    session: SessionDependency,
) -> ManagementOverview:
    counts = dict(
        session.execute(
            select(ManagementRecord.module, func.count(ManagementRecord.id)).group_by(
                ManagementRecord.module
            )
        ).all()
    )
    fact_status_counts = dict(
        session.execute(
            select(ManagementRecord.fact_status, func.count(ManagementRecord.id)).group_by(
                ManagementRecord.fact_status
            )
        ).all()
    )
    return ManagementOverview(
        total_records=sum(counts.values()),
        private_records=session.scalar(
            select(func.count(ManagementRecord.id)).where(
                ManagementRecord.sensitivity == "PRIVATE_MANAGEMENT"
            )
        )
        or 0,
        pending_confirmation=session.scalar(
            select(func.count(ManagementRecord.id)).where(
                ManagementRecord.fact_status.in_(PENDING_FACT_STATUSES)
            )
        )
        or 0,
        by_module={module: counts.get(module, 0) for module in MODULES},
        by_fact_status={
            fact_status: fact_status_counts.get(fact_status, 0)
            for fact_status in FACT_STATUSES
        },
        latest_update=session.scalar(select(func.max(ManagementRecord.updated_at))),
        sources=session.scalar(select(func.count(ManagementSource.id))) or 0,
    )


@router.get("/records")
def list_management_records(
    _: OpsAccess,
    session: SessionDependency,
    module: Annotated[ManagementModule | None, Query()] = None,
) -> list[ManagementRecordResponse]:
    if module == "PEOPLE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "PRIVATE_MODULE_REQUIRES_EXPLICIT_ENDPOINT"},
        )
    statement = (
        select(ManagementRecord, ManagementSource.name)
        .join(ManagementSource, ManagementSource.id == ManagementRecord.source_id)
        .where(
            ManagementRecord.module != "PEOPLE",
            ManagementRecord.sensitivity != "PRIVATE_MANAGEMENT",
        )
        .order_by(ManagementRecord.module, ManagementRecord.title)
    )
    if module is not None:
        statement = statement.where(ManagementRecord.module == module)
    return [_response(record, source_name) for record, source_name in session.execute(statement)]


@router.get("/people")
def list_private_people_records(
    _: OpsAccess,
    session: SessionDependency,
) -> list[ManagementRecordResponse]:
    statement = (
        select(ManagementRecord, ManagementSource.name)
        .join(ManagementSource, ManagementSource.id == ManagementRecord.source_id)
        .where(
            ManagementRecord.module == "PEOPLE",
            ManagementRecord.sensitivity == "PRIVATE_MANAGEMENT",
        )
        .order_by(ManagementRecord.title)
    )
    return [_response(record, source_name) for record, source_name in session.execute(statement)]


@router.post("/imports")
def import_management_records(
    payload: ManagementImportRequest,
    _: OpsAccess,
    session: SessionDependency,
) -> ManagementImportResult:
    payload_json = payload.model_dump(mode="json")
    checksum = hashlib.sha256(
        json.dumps(
            payload_json,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    duplicate = session.scalar(
        select(ManagementImportBatch).where(
            ManagementImportBatch.checksum_sha256 == checksum
        )
    )
    if duplicate is not None:
        return ManagementImportResult(
            batch_id=duplicate.id,
            duplicate=True,
            created=0,
            updated=0,
            unchanged=duplicate.record_count,
            total_records=duplicate.record_count,
        )

    source = session.scalar(
        select(ManagementSource).where(ManagementSource.code == payload.source_code)
    )
    if source is None:
        source = ManagementSource(
            code=payload.source_code,
            name=payload.source_name,
            source_type=payload.source_type,
            authority_scope=payload.authority_scope,
            sync_mode="MANUAL_REVIEW",
            retention_policy="REFERENCE_ONLY",
            contains_sensitive_data=any(item.module == "PEOPLE" for item in payload.records),
            source_url=payload.source_url,
        )
        session.add(source)
        session.flush()
    else:
        source.name = payload.source_name
        source.source_type = payload.source_type
        source.authority_scope = payload.authority_scope
        source.source_url = payload.source_url
        source.contains_sensitive_data = source.contains_sensitive_data or any(
            item.module == "PEOPLE" for item in payload.records
        )

    batch = ManagementImportBatch(
        source_id=source.id,
        source_version=payload.source_version,
        checksum_sha256=checksum,
        record_count=len(payload.records),
    )
    session.add(batch)
    session.flush()

    created = 0
    updated = 0
    unchanged = 0
    for item in payload.records:
        incoming = _incoming_snapshot(item, payload.source_version)
        existing = session.scalar(
            select(ManagementRecord).where(
                ManagementRecord.source_id == source.id,
                ManagementRecord.source_record_key == item.source_record_key,
            )
        )
        if existing is not None and payload.source_version < existing.source_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "STALE_MANAGEMENT_SOURCE_VERSION",
                    "source_record_key": item.source_record_key,
                },
            )
        if existing is not None and payload.source_version == existing.source_version:
            if _record_snapshot(existing) != incoming:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error_code": "MANAGEMENT_RECORD_VERSION_CONFLICT",
                        "source_record_key": item.source_record_key,
                    },
                )
            unchanged += 1
            continue

        if existing is None:
            record = ManagementRecord(
                source_id=source.id,
                import_batch_id=batch.id,
                source_record_key=item.source_record_key,
                source_version=payload.source_version,
                module=item.module,
                title=item.title,
                summary=item.summary,
                subject_type=item.subject_type,
                subject_key=item.subject_key,
                fact_status=item.fact_status,
                lifecycle_status=item.lifecycle_status,
                sensitivity=(
                    "PRIVATE_MANAGEMENT" if item.module == "PEOPLE" else item.sensitivity
                ),
                observed_at=item.observed_at,
                effective_from=item.effective_from,
                effective_to=item.effective_to,
                evidence_ref=item.evidence_ref,
                payload_json=item.payload,
            )
            session.add(record)
            session.flush()
            session.add(
                ManagementRecordAudit(
                    record_id=record.id,
                    event_type="IMPORTED",
                    after_json=incoming,
                )
            )
            created += 1
            continue

        before = _record_snapshot(existing)
        existing.import_batch_id = batch.id
        existing.source_version = payload.source_version
        existing.module = item.module
        existing.title = item.title
        existing.summary = item.summary
        existing.subject_type = item.subject_type
        existing.subject_key = item.subject_key
        existing.fact_status = item.fact_status
        existing.lifecycle_status = item.lifecycle_status
        existing.sensitivity = (
            "PRIVATE_MANAGEMENT" if item.module == "PEOPLE" else item.sensitivity
        )
        existing.observed_at = item.observed_at
        existing.effective_from = item.effective_from
        existing.effective_to = item.effective_to
        existing.evidence_ref = item.evidence_ref
        existing.payload_json = item.payload
        session.add(
            ManagementRecordAudit(
                record_id=existing.id,
                event_type="UPDATED_FROM_SOURCE",
                before_json=before,
                after_json=incoming,
            )
        )
        updated += 1

    session.commit()
    return ManagementImportResult(
        batch_id=batch.id,
        duplicate=False,
        created=created,
        updated=updated,
        unchanged=unchanged,
        total_records=len(payload.records),
    )
