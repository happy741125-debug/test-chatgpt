from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Event

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.gateway import AIGateway
from app.ai.providers import RuleBasedAIProvider
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db import Database
from app.intelligence.materializer import IntelligenceMaterializer, IntelligencePipeline
from app.models import JobStatus, ProcessingJob
from app.queue import JobQueue, RedisJobQueue
from app.services.context import ContextBuilder, ContextFinalizer

logger = logging.getLogger(__name__)
JobHandler = Callable[[str, dict[str, object]], None]


class JobRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        queue: JobQueue,
        handler: JobHandler,
        *,
        retry_base_seconds: float = 5,
    ) -> None:
        self.session_factory = session_factory
        self.queue = queue
        self.handler = handler
        self.retry_base_seconds = retry_base_seconds

    def process_once(self, timeout_seconds: int = 1) -> bool:
        message = self.queue.pop(timeout_seconds=timeout_seconds)
        if message is None:
            return False

        with self.session_factory() as session:
            job = session.get(ProcessingJob, message.job_id)
            terminal_statuses = {JobStatus.PROCESSED.value, JobStatus.DEAD_LETTER.value}
            if job is None or job.status in terminal_statuses:
                return True

            job.status = JobStatus.PROCESSING.value
            session.commit()
            try:
                self.handler(job.job_type, dict(job.payload_json))
            except Exception as exc:  # noqa: BLE001 - job boundary must contain all failures
                self._handle_failure(session, job, exc)
            else:
                job.status = JobStatus.PROCESSED.value
                job.last_error = None
                job.updated_at = datetime.now(UTC)
                session.commit()
        return True

    def _handle_failure(self, session: Session, job: ProcessingJob, exc: Exception) -> None:
        job.attempts += 1
        job.last_error = str(exc)[:4000]
        job.updated_at = datetime.now(UTC)
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.DEAD_LETTER.value
            session.commit()
            self.queue.dead_letter(job.id, job.last_error)
            return

        base_delay = self.retry_base_seconds * (2 ** (job.attempts - 1))
        jitter = random.uniform(0, base_delay * 0.2) if base_delay else 0
        delay = base_delay + jitter
        job.available_at = datetime.now(UTC) + timedelta(seconds=delay)
        job.status = JobStatus.RETRY_SCHEDULED.value
        session.commit()
        self.queue.schedule_retry(job.id, time.time() + delay)


class ContextPipelineHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        queue: JobQueue,
        *,
        window_minutes: int,
        max_messages: int,
        buffer_seconds: int,
        analysis_handler: Callable[[str], object] | None = None,
    ) -> None:
        self.queue = queue
        self.analysis_handler = analysis_handler
        self.builder = ContextBuilder(
            session_factory,
            window_minutes=window_minutes,
            max_messages=max_messages,
        )
        self.finalizer = ContextFinalizer(session_factory, buffer_seconds=buffer_seconds)

    def __call__(self, job_type: str, payload: dict[str, object]) -> None:
        if job_type == "build_context":
            message_id = payload.get("message_id")
            if not isinstance(message_id, str):
                raise ValueError("build_context job requires message_id")
            result = self.builder.add_message(message_id)
            self._publish(result.analysis_job_ids)
            return
        if job_type == "analyze_context":
            context_id = payload.get("context_id")
            if not isinstance(context_id, str):
                raise ValueError("analyze_context job requires context_id")
            if self.analysis_handler is None:
                logger.info("Context ready for AI analysis: %s", context_id)
            else:
                self.analysis_handler(context_id)
            return
        raise ValueError(f"Unsupported job type: {job_type}")

    def finalize_due(self) -> int:
        job_ids = self.finalizer.finalize_due()
        self._publish(job_ids)
        return len(job_ids)

    def _publish(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            try:
                self.queue.publish(job_id)
            except Exception:  # noqa: BLE001 - durable DB job remains available for replay
                logger.exception("Unable to publish durable context job", extra={"job_id": job_id})


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings.database_url)
    queue = RedisJobQueue(
        settings.redis_url,
        queue_key=settings.redis_queue_key,
        retry_key=settings.redis_retry_key,
        dlq_key=settings.redis_dlq_key,
    )
    run_worker_loop(settings, database, queue)


def build_context_pipeline(
    settings: Settings,
    database: Database,
    queue: JobQueue,
) -> ContextPipelineHandler:
    analysis_handler: Callable[[str], object] | None = None
    if settings.ai_provider == "rule-based":
        primary = RuleBasedAIProvider()
        gateway = AIGateway(database.session_factory, primary)
        materializer = IntelligenceMaterializer(database.session_factory)
        if settings.gemini_shadow_active:
            from app.ai.gemini import GeminiAIProvider
            from app.ai.shadow import ShadowComparator, ShadowExtractionPipeline

            comparator = ShadowComparator(
                database.session_factory,
                GeminiAIProvider(settings.gemini_api_key, model=settings.gemini_model),
                primary_provider_name=primary.name,
                primary_model=primary.model,
            )
            analysis_handler = ShadowExtractionPipeline(gateway, materializer, comparator)
        else:
            analysis_handler = IntelligencePipeline(gateway, materializer)
    elif settings.ai_provider != "disabled":
        raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")
    return ContextPipelineHandler(
        database.session_factory,
        queue,
        window_minutes=settings.context_window_minutes,
        max_messages=settings.context_max_messages,
        buffer_seconds=settings.context_buffer_seconds,
        analysis_handler=analysis_handler,
    )


def run_worker_loop(
    settings: Settings,
    database: Database,
    queue: JobQueue,
    *,
    stop_event: Event | None = None,
) -> None:
    pipeline = build_context_pipeline(settings, database, queue)
    runner = JobRunner(database.session_factory, queue, pipeline)
    recovered = recover_pending_jobs(database.session_factory, queue)
    logger.info(
        "Worker started",
        extra={"ai_provider": settings.ai_provider, "recovered_jobs": recovered},
    )
    while stop_event is None or not stop_event.is_set():
        processed = runner.process_once(timeout_seconds=5)
        if not processed:
            pipeline.finalize_due()
    logger.info("Worker stopped")


def recover_pending_jobs(
    session_factory: sessionmaker[Session],
    queue: JobQueue,
    *,
    now: datetime | None = None,
    limit: int = 500,
) -> int:
    current = now or datetime.now(UTC)
    with session_factory() as session:
        jobs = session.scalars(
            select(ProcessingJob)
            .where(
                or_(
                    ProcessingJob.status.in_(
                        [JobStatus.QUEUED.value, JobStatus.PROCESSING.value]
                    ),
                    and_(
                        ProcessingJob.status == JobStatus.RETRY_SCHEDULED.value,
                        ProcessingJob.available_at <= current,
                    ),
                )
            )
            .order_by(ProcessingJob.available_at, ProcessingJob.created_at)
            .limit(limit)
        ).all()
        for job in jobs:
            job.status = JobStatus.QUEUED.value
            job.updated_at = current
        session.commit()

    published = 0
    for job in jobs:
        try:
            queue.publish(job.id)
            published += 1
        except Exception:  # noqa: BLE001 - durable DB job remains queued for recovery
            logger.exception("Unable to recover durable job", extra={"job_id": job.id})
    return published


if __name__ == "__main__":
    main()
