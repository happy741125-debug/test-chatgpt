from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import Database
from app.models import JobStatus, ProcessingJob
from app.queue import InMemoryJobQueue
from app.worker import JobRunner, recover_pending_jobs


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


def test_worker_startup_recovers_durable_pending_jobs() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    queue = InMemoryJobQueue()
    now = datetime(2026, 9, 7, 1, 30, tzinfo=UTC)

    with database.session_factory() as session:
        jobs = [
            ProcessingJob(
                job_type="build_context",
                idempotency_key=f"recovery:{status}",
                payload_json={"message_id": status},
                status=status,
                available_at=available_at,
            )
            for status, available_at in [
                (JobStatus.QUEUED.value, now),
                (JobStatus.PROCESSING.value, now),
                (JobStatus.RETRY_SCHEDULED.value, now - timedelta(seconds=1)),
                (JobStatus.PROCESSED.value, now),
            ]
        ]
        future_retry = ProcessingJob(
            job_type="build_context",
            idempotency_key="recovery:future",
            payload_json={"message_id": "future"},
            status=JobStatus.RETRY_SCHEDULED.value,
            available_at=now + timedelta(minutes=5),
        )
        session.add_all([*jobs, future_retry])
        session.commit()
        expected_ids = {job.id for job in jobs[:3]}

    assert recover_pending_jobs(database.session_factory, queue, now=now) == 3
    assert {message.job_id for message in queue.ready} == expected_ids

    with database.session_factory() as session:
        recovered = session.scalars(
            select(ProcessingJob).where(ProcessingJob.id.in_(expected_ids))
        ).all()
        assert all(job.status == JobStatus.QUEUED.value for job in recovered)
        stored_future_retry = session.get(ProcessingJob, future_retry.id)
        assert stored_future_retry is not None
        assert stored_future_retry.status == JobStatus.RETRY_SCHEDULED.value

    database.engine.dispose()
