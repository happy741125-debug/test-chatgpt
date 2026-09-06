from __future__ import annotations

from datetime import UTC, datetime

from app.models import JobStatus, ProcessingJob

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _dead_job(database) -> str:
    with database.session_factory() as session:
        job = ProcessingJob(
            job_type="build_context",
            idempotency_key=f"dead:{datetime.now(UTC).timestamp()}",
            payload_json={"message_id": "missing"},
            status=JobStatus.DEAD_LETTER.value,
            attempts=5,
            max_attempts=5,
            last_error="test failure",
        )
        session.add(job)
        session.commit()
        return job.id


def test_ops_endpoints_require_admin_token(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/ops/jobs/dead-letter")

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "OPS_ACCESS_DENIED"


def test_dead_letter_job_can_be_replayed(test_context) -> None:
    client, database, queue = test_context
    job_id = _dead_job(database)

    listed = client.get("/ops/jobs/dead-letter", headers=OPS_HEADERS)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == job_id
    assert listed.json()[0]["status"] == JobStatus.DEAD_LETTER.value

    retried = client.post(f"/ops/jobs/{job_id}/retry", headers=OPS_HEADERS)
    assert retried.status_code == 200
    assert retried.json()["status"] == JobStatus.QUEUED.value
    assert retried.json()["attempts"] == 0
    assert queue.ready[0].job_id == job_id


def test_non_failed_job_cannot_be_replayed(test_context) -> None:
    client, database, _ = test_context
    with database.session_factory() as session:
        job = ProcessingJob(
            job_type="build_context",
            idempotency_key="queued:test",
            payload_json={"message_id": "test"},
            status=JobStatus.QUEUED.value,
        )
        session.add(job)
        session.commit()
        job_id = job.id

    response = client.post(f"/ops/jobs/{job_id}/retry", headers=OPS_HEADERS)

    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "JOB_NOT_RETRYABLE"


def test_missing_job_returns_not_found(test_context) -> None:
    client, _, _ = test_context

    response = client.post("/ops/jobs/missing/retry", headers=OPS_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "JOB_NOT_FOUND"


def test_metrics_endpoint_exposes_line_counters(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "workhub_line_events_accepted_total" in response.text
    assert "workhub_line_invalid_signatures_total" in response.text
