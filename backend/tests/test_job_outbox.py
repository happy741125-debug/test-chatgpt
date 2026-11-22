from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.db import Database
from app.models import JobStatus, ProcessingJob, Workspace
from app.services.job_outbox import (
    claim_jobs,
    complete_job,
    enqueue_job,
    reap_expired_claims,
)
from app.worker import PostgresOutboxRunner


def test_business_data_and_outbox_roll_back_together(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = Workspace(slug="atomic", name="Atomic")
        session.add(workspace)
        session.flush()
        enqueue_job(
            session,
            workspace_id=workspace.id,
            job_type="normalize_source_record",
            idempotency_key="atomic:record-1",
            payload={"record_id": "record-1"},
        )
        session.rollback()

    with database.session_factory() as session:
        assert session.scalar(select(Workspace).where(Workspace.slug == "atomic")) is None
        assert (
            session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.idempotency_key == "atomic:record-1"
                )
            )
            is None
        )


def test_enqueue_is_idempotent_and_rejects_conflicting_payload(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        first = enqueue_job(
            session,
            job_type="sync_source",
            idempotency_key="sync:source-1",
            payload={"source_id": "source-1"},
        )
        duplicate = enqueue_job(
            session,
            job_type="sync_source",
            idempotency_key="sync:source-1",
            payload={"source_id": "source-1"},
        )
        assert first.created is True
        assert duplicate.created is False
        assert duplicate.job.id == first.job.id

        with pytest.raises(ValueError, match="JOB_IDEMPOTENCY_CONFLICT"):
            enqueue_job(
                session,
                job_type="sync_source",
                idempotency_key="sync:source-1",
                payload={"source_id": "different-source"},
            )


def test_database_runner_completes_due_job(test_context) -> None:
    _, database, _ = test_context
    seen: list[tuple[str, dict[str, object]]] = []
    with database.session_factory() as session:
        job = enqueue_job(
            session,
            job_type="normalize_source_record",
            idempotency_key="success:record-1",
            payload={"record_id": "record-1"},
        ).job
        session.commit()
        job_id = job.id

    runner = PostgresOutboxRunner(
        database.session_factory,
        lambda job_type, payload: seen.append((job_type, payload)),
        worker_id="worker-success",
    )
    assert runner.process_once() == 1
    assert seen == [("normalize_source_record", {"record_id": "record-1"})]

    with database.session_factory() as session:
        stored = session.get(ProcessingJob, job_id)
        assert stored is not None
        assert stored.status == JobStatus.PROCESSED.value
        assert stored.completed_at is not None
        assert stored.claim_token is None


def test_database_runner_retries_with_backoff_then_dead_letters(test_context) -> None:
    _, database, _ = test_context
    now = datetime(2026, 11, 22, 8, 0, tzinfo=UTC)
    with database.session_factory() as session:
        job = enqueue_job(
            session,
            job_type="sync_source",
            idempotency_key="failure:source-1",
            payload={"source_id": "source-1"},
            max_attempts=2,
            available_at=now,
        ).job
        session.commit()
        job_id = job.id

    def fail(_job_type: str, _payload: dict[str, object]) -> None:
        raise RuntimeError("connector unavailable")

    runner = PostgresOutboxRunner(
        database.session_factory,
        fail,
        worker_id="worker-failure",
        retry_base_seconds=10,
    )
    assert runner.process_once(now=now) == 1
    with database.session_factory() as session:
        retrying = session.get(ProcessingJob, job_id)
        assert retrying is not None
        assert retrying.status == JobStatus.RETRY_SCHEDULED.value
        assert retrying.attempts == 1
        assert retrying.available_at.replace(tzinfo=UTC) == now + timedelta(seconds=10)

    assert runner.process_once(now=now + timedelta(seconds=9)) == 0
    assert runner.process_once(now=now + timedelta(seconds=10)) == 1
    with database.session_factory() as session:
        dead = session.get(ProcessingJob, job_id)
        assert dead is not None
        assert dead.status == JobStatus.DEAD_LETTER.value
        assert dead.attempts == 2
        assert dead.last_error == "connector unavailable"


def test_expired_claim_recovers_and_old_worker_cannot_complete(test_context) -> None:
    _, database, _ = test_context
    now = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
    with database.session_factory() as session:
        enqueue_job(
            session,
            job_type="sync_source",
            idempotency_key="timeout:source-1",
            payload={"source_id": "source-1"},
            available_at=now,
        )
        session.commit()

    with database.session_factory() as session:
        claimed = claim_jobs(
            session,
            worker_id="worker-old",
            lease_seconds=5,
            now=now,
        )
        assert len(claimed) == 1
        job_id = claimed[0].id
        old_token = claimed[0].claim_token or ""
        session.commit()

    recovered_at = now + timedelta(seconds=6)
    with database.session_factory() as session:
        expired = reap_expired_claims(
            session,
            now=recovered_at,
            retry_base_seconds=0,
        )
        assert [job.id for job in expired] == [job_id]
        session.commit()

    with database.session_factory() as session:
        recovered = session.get(ProcessingJob, job_id)
        assert recovered is not None
        assert recovered.status == JobStatus.RETRY_SCHEDULED.value
        assert recovered.attempts == 1
        with pytest.raises(ValueError, match="STALE_JOB_CLAIM"):
            complete_job(
                recovered,
                worker_id="worker-old",
                claim_token=old_token,
                now=recovered_at,
            )

    with database.session_factory() as session:
        reclaimed = claim_jobs(session, worker_id="worker-new", now=recovered_at)
        assert [job.id for job in reclaimed] == [job_id]
        assert reclaimed[0].claim_token != old_token


def test_claimed_job_is_not_returned_to_second_worker(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        enqueue_job(
            session,
            job_type="sync_source",
            idempotency_key="claim:source-1",
            payload={"source_id": "source-1"},
        )
        session.commit()

    with database.session_factory() as session:
        first = claim_jobs(session, worker_id="worker-a")
        session.commit()
    with database.session_factory() as session:
        second = claim_jobs(session, worker_id="worker-b")

    assert len(first) == 1
    assert second == []


@pytest.mark.skipif(
    not os.getenv("AI_COS_POSTGRES_TEST_URL", "").startswith("postgresql"),
    reason="Dedicated PostgreSQL CI URL is required",
)
def test_postgres_skip_locked_allows_only_one_concurrent_claim() -> None:
    database = Database(os.environ["AI_COS_POSTGRES_TEST_URL"])
    key = f"parallel:{uuid.uuid4()}"
    with database.session_factory() as session:
        enqueue_job(
            session,
            job_type="parallel_test",
            idempotency_key=key,
            payload={"safe_fixture": True},
        )
        session.commit()

    start = threading.Barrier(2)
    locked = threading.Barrier(2)
    claimed_ids: list[str] = []
    failures: list[Exception] = []

    def claim(worker_id: str) -> None:
        try:
            with database.session_factory() as session:
                start.wait(timeout=10)
                jobs = claim_jobs(session, worker_id=worker_id, limit=1)
                claimed_ids.extend(job.id for job in jobs)
                locked.wait(timeout=10)
                session.commit()
        except Exception as exc:  # noqa: BLE001 - preserve thread failures for assertion
            failures.append(exc)

    threads = [
        threading.Thread(target=claim, args=("worker-a",)),
        threading.Thread(target=claim, args=("worker-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    try:
        assert failures == []
        assert all(not thread.is_alive() for thread in threads)
        assert len(claimed_ids) == 1
    finally:
        with database.session_factory() as session:
            session.execute(
                delete(ProcessingJob).where(ProcessingJob.idempotency_key == key)
            )
            session.commit()
        database.engine.dispose()
