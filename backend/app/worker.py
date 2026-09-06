from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import Database
from app.models import JobStatus, ProcessingJob
from app.queue import JobQueue, RedisJobQueue

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

        delay = self.retry_base_seconds * (2 ** (job.attempts - 1))
        job.available_at = datetime.now(UTC) + timedelta(seconds=delay)
        job.status = JobStatus.RETRY_SCHEDULED.value
        session.commit()
        self.queue.schedule_retry(job.id, time.time() + delay)


def placeholder_context_handler(job_type: str, payload: dict[str, object]) -> None:
    if job_type != "build_context":
        raise ValueError(f"Unsupported job type: {job_type}")
    logger.info("Context job received for message_id=%s", payload.get("message_id"))


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
    runner = JobRunner(database.session_factory, queue, placeholder_context_handler)
    logger.info("Worker started")
    while True:
        runner.process_once(timeout_seconds=5)


if __name__ == "__main__":
    main()
