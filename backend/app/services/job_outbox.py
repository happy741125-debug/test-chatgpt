from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import JobStatus, ProcessingJob, utc_now


@dataclass(frozen=True)
class EnqueueResult:
    job: ProcessingJob
    created: bool


def enqueue_job(
    session: Session,
    *,
    job_type: str,
    idempotency_key: str,
    payload: dict[str, object],
    workspace_id: str | None = None,
    correlation_id: str | None = None,
    max_attempts: int = 5,
    available_at: datetime | None = None,
) -> EnqueueResult:
    """Stage a durable job in the caller's current database transaction.

    This function intentionally never commits. The business record and its job therefore
    succeed or roll back together when callers use the same session.
    """

    normalized_type = job_type.strip()
    normalized_key = idempotency_key.strip()
    if not normalized_type:
        raise ValueError("JOB_TYPE_REQUIRED")
    if not normalized_key:
        raise ValueError("JOB_IDEMPOTENCY_KEY_REQUIRED")
    if max_attempts < 1:
        raise ValueError("JOB_MAX_ATTEMPTS_INVALID")

    existing = session.scalar(
        select(ProcessingJob).where(ProcessingJob.idempotency_key == normalized_key)
    )
    if existing is not None:
        if existing.job_type != normalized_type or dict(existing.payload_json) != payload:
            raise ValueError("JOB_IDEMPOTENCY_CONFLICT")
        return EnqueueResult(job=existing, created=False)

    job = ProcessingJob(
        workspace_id=workspace_id,
        job_type=normalized_type,
        idempotency_key=normalized_key,
        correlation_id=correlation_id,
        payload_json=payload,
        max_attempts=max_attempts,
        available_at=available_at or utc_now(),
        status=JobStatus.QUEUED.value,
    )
    session.add(job)
    session.flush()
    return EnqueueResult(job=job, created=True)


def claim_jobs(
    session: Session,
    *,
    worker_id: str,
    limit: int = 10,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> list[ProcessingJob]:
    """Claim due jobs with row locks; PostgreSQL workers skip rows locked by peers."""

    normalized_worker = worker_id.strip()
    if not normalized_worker:
        raise ValueError("WORKER_ID_REQUIRED")
    if limit < 1:
        raise ValueError("CLAIM_LIMIT_INVALID")
    if lease_seconds < 1:
        raise ValueError("CLAIM_LEASE_INVALID")

    current = now or utc_now()
    due_status = or_(
        ProcessingJob.status == JobStatus.QUEUED.value,
        ProcessingJob.status == JobStatus.RETRY_SCHEDULED.value,
    )
    statement = (
        select(ProcessingJob)
        .where(and_(due_status, ProcessingJob.available_at <= current))
        .order_by(ProcessingJob.available_at, ProcessingJob.created_at, ProcessingJob.id)
        .limit(limit)
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    else:
        statement = statement.with_for_update()

    jobs = list(session.scalars(statement).all())
    for job in jobs:
        job.status = JobStatus.PROCESSING.value
        job.claimed_by = normalized_worker
        job.claim_token = str(uuid.uuid4())
        job.claimed_at = current
        job.claim_expires_at = current + timedelta(seconds=lease_seconds)
        job.updated_at = current
    session.flush()
    return jobs


def complete_job(
    job: ProcessingJob,
    *,
    worker_id: str,
    claim_token: str,
    now: datetime | None = None,
) -> None:
    _require_active_claim(job, worker_id=worker_id, claim_token=claim_token)
    current = now or utc_now()
    job.status = JobStatus.PROCESSED.value
    job.last_error = None
    job.completed_at = current
    job.updated_at = current
    _clear_claim(job)


def fail_job(
    job: ProcessingJob,
    *,
    worker_id: str,
    claim_token: str,
    error: Exception | str,
    retry_base_seconds: float = 5,
    now: datetime | None = None,
) -> None:
    _require_active_claim(job, worker_id=worker_id, claim_token=claim_token)
    current = now or utc_now()
    job.attempts += 1
    job.last_error = str(error)[:4000]
    job.updated_at = current
    job.completed_at = None
    _clear_claim(job)
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.DEAD_LETTER.value
        return

    job.status = JobStatus.RETRY_SCHEDULED.value
    job.available_at = current + timedelta(
        seconds=_retry_delay(retry_base_seconds, job.attempts)
    )


def reap_expired_claims(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
    retry_base_seconds: float = 5,
) -> list[ProcessingJob]:
    """Move abandoned claims to retry or dead-letter after a worker stops responding."""

    current = now or utc_now()
    statement = (
        select(ProcessingJob)
        .where(
            ProcessingJob.status == JobStatus.PROCESSING.value,
            ProcessingJob.claim_expires_at.is_not(None),
            ProcessingJob.claim_expires_at <= current,
        )
        .order_by(ProcessingJob.claim_expires_at, ProcessingJob.id)
        .limit(limit)
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    else:
        statement = statement.with_for_update()

    expired = list(session.scalars(statement).all())
    for job in expired:
        job.attempts += 1
        job.last_error = "CLAIM_LEASE_EXPIRED"
        job.updated_at = current
        _clear_claim(job)
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.DEAD_LETTER.value
        else:
            job.status = JobStatus.RETRY_SCHEDULED.value
            job.available_at = current + timedelta(
                seconds=_retry_delay(retry_base_seconds, job.attempts)
            )
    session.flush()
    return expired


def _require_active_claim(
    job: ProcessingJob, *, worker_id: str, claim_token: str
) -> None:
    if (
        job.status != JobStatus.PROCESSING.value
        or job.claimed_by != worker_id
        or job.claim_token != claim_token
    ):
        raise ValueError("STALE_JOB_CLAIM")


def _clear_claim(job: ProcessingJob) -> None:
    job.claimed_by = None
    job.claim_token = None
    job.claimed_at = None
    job.claim_expires_at = None


def _retry_delay(base_seconds: float, attempts: int) -> float:
    if base_seconds < 0:
        raise ValueError("RETRY_BASE_SECONDS_INVALID")
    return base_seconds * (2 ** max(0, attempts - 1))
