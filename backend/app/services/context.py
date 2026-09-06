from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Context,
    ContextMessage,
    ContextStatus,
    JobStatus,
    Message,
    ProcessingJob,
    ProcessingStatus,
)


@dataclass
class ContextBuildResult:
    context_id: str
    created: bool
    analysis_job_ids: list[str] = field(default_factory=list)


class ContextBuilder:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        window_minutes: int = 15,
        max_messages: int = 30,
    ) -> None:
        self.session_factory = session_factory
        self.window = timedelta(minutes=window_minutes)
        self.max_messages = max_messages

    def add_message(self, message_id: str) -> ContextBuildResult:
        with self.session_factory() as session:
            existing_context_id = session.scalar(
                select(ContextMessage.context_id).where(ContextMessage.message_id == message_id)
            )
            if existing_context_id is not None:
                return ContextBuildResult(context_id=existing_context_id, created=False)

            message = session.get(Message, message_id)
            if message is None:
                raise ValueError(f"Message not found: {message_id}")

            latest = session.scalar(
                select(Context)
                .where(
                    Context.channel_id == message.channel_id,
                    Context.status == ContextStatus.OPEN.value,
                )
                .order_by(Context.end_at.desc())
                .limit(1)
            )

            analysis_job_ids: list[str] = []
            if latest is not None and not self._fits(latest, message):
                latest.status = ContextStatus.READY.value
                job = _ensure_analysis_job(session, latest)
                if job is not None:
                    analysis_job_ids.append(job.id)
                latest = None

            created = latest is None
            context = latest or Context(
                channel_id=message.channel_id,
                start_at=message.source_created_at,
                end_at=message.source_created_at,
                status=ContextStatus.OPEN.value,
            )
            if created:
                session.add(context)
                session.flush()

            sequence = context.message_count + 1
            session.add(
                ContextMessage(
                    context_id=context.id,
                    message_id=message.id,
                    sequence=sequence,
                    included_reason="TIME_WINDOW",
                )
            )
            context.start_at = min(
                _as_utc(context.start_at),
                _as_utc(message.source_created_at),
            )
            context.end_at = max(
                _as_utc(context.end_at),
                _as_utc(message.source_created_at),
            )
            context.message_count += 1
            context.token_estimate += _estimate_tokens(message.text)
            message.processing_status = ProcessingStatus.CONTEXT_PENDING.value
            session.commit()
            return ContextBuildResult(
                context_id=context.id,
                created=created,
                analysis_job_ids=analysis_job_ids,
            )

    def _fits(self, context: Context, message: Message) -> bool:
        source_time = _as_utc(message.source_created_at)
        start_at = _as_utc(context.start_at)
        end_at = _as_utc(context.end_at)
        return (
            source_time >= end_at
            and source_time - start_at <= self.window
            and context.message_count < self.max_messages
        )


class ContextFinalizer:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        buffer_seconds: int = 180,
    ) -> None:
        self.session_factory = session_factory
        self.buffer = timedelta(seconds=buffer_seconds)

    def finalize_due(self, *, now: datetime | None = None) -> list[str]:
        current_time = _as_utc(now or datetime.now(UTC))
        cutoff = current_time - self.buffer
        job_ids: list[str] = []
        with self.session_factory() as session:
            contexts = session.scalars(
                select(Context).where(
                    Context.status == ContextStatus.OPEN.value,
                    Context.end_at <= cutoff,
                )
            ).all()
            for context in contexts:
                context.status = ContextStatus.READY.value
                job = _ensure_analysis_job(session, context)
                if job is not None:
                    job_ids.append(job.id)
            session.commit()
        return job_ids


def _ensure_analysis_job(session: Session, context: Context) -> ProcessingJob | None:
    idempotency_key = f"analyze_context:{context.id}:v{context.version}"
    existing = session.scalar(
        select(ProcessingJob.id).where(ProcessingJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return None
    job = ProcessingJob(
        job_type="analyze_context",
        idempotency_key=idempotency_key,
        payload_json={"context_id": context.id, "version": context.version},
        status=JobStatus.QUEUED.value,
    )
    session.add(job)
    session.flush()
    return job


def _estimate_tokens(text: str | None) -> int:
    if not text:
        return 1
    return max(1, (len(text) + 3) // 4)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
