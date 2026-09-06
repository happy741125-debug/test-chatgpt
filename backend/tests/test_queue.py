from __future__ import annotations

from sqlalchemy import select

from app.db import Database
from app.models import JobStatus, ProcessingJob
from app.queue import InMemoryJobQueue
from app.worker import JobRunner


def test_failed_job_retries_then_moves_to_dead_letter() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    queue = InMemoryJobQueue()

    with database.session_factory() as session:
        job = ProcessingJob(
            job_type="build_context",
            idempotency_key="build_context:test-message",
            payload_json={"message_id": "test-message"},
            max_attempts=2,
        )
        session.add(job)
        session.commit()
        job_id = job.id

    queue.publish(job_id)

    def failing_handler(job_type: str, payload: dict[str, object]) -> None:
        raise RuntimeError(f"failed {job_type} for {payload['message_id']}")

    runner = JobRunner(
        database.session_factory,
        queue,
        failing_handler,
        retry_base_seconds=0,
    )

    assert runner.process_once(timeout_seconds=0) is True
    assert len(queue.retries) == 1
    assert runner.process_once(timeout_seconds=0) is True

    with database.session_factory() as session:
        stored = session.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
        assert stored is not None
        assert stored.status == JobStatus.DEAD_LETTER.value
        assert stored.attempts == 2
        assert "failed build_context" in (stored.last_error or "")

    assert len(queue.dead_letters) == 1
    assert queue.dead_letters[0]["job_id"] == job_id
    database.engine.dispose()
