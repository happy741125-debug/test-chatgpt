from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.line.security import make_signature
from app.models import Context, ContextMessage, ContextStatus, ProcessingJob
from app.services.context import ContextFinalizer
from app.worker import ContextPipelineHandler, JobRunner

SECRET = "test-channel-secret"


def _payload(event_id: str, message_id: str, text: str, timestamp: int) -> dict[str, object]:
    return {
        "events": [
            {
                "type": "message",
                "timestamp": timestamp,
                "source": {"type": "group", "groupId": "C-context", "userId": "U-user"},
                "webhookEventId": event_id,
                "message": {"id": message_id, "type": "text", "text": text},
            }
        ]
    }


def _post(client, payload: dict[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": make_signature(body, SECRET),
        },
    )
    assert response.status_code == 200


def _runner(database, queue) -> JobRunner:
    pipeline = ContextPipelineHandler(
        database.session_factory,
        queue,
        window_minutes=15,
        max_messages=30,
        buffer_seconds=180,
    )
    return JobRunner(database.session_factory, queue, pipeline, retry_base_seconds=0)


def test_related_messages_form_one_traceable_context(test_context) -> None:
    client, database, queue = test_context
    base = datetime.now(UTC).replace(microsecond=0)
    messages = [
        ("event-context-1", "message-context-1", "貨到了嗎？", base),
        ("event-context-2", "message-context-2", "還沒", base + timedelta(minutes=1)),
        ("event-context-3", "message-context-3", "廠商說星期四到", base + timedelta(minutes=2)),
    ]
    for event_id, message_id, text, created_at in messages:
        _post(client, _payload(event_id, message_id, text, int(created_at.timestamp() * 1000)))

    runner = _runner(database, queue)
    for _ in messages:
        assert runner.process_once(timeout_seconds=0) is True

    with database.session_factory() as session:
        contexts = session.scalars(select(Context)).all()
        assert len(contexts) == 1
        context = contexts[0]
        assert context.status == ContextStatus.OPEN.value
        assert context.message_count == 3
        assert session.scalar(select(func.count()).select_from(ContextMessage)) == 3
        context_id = context.id

    detail = client.get(f"/api/contexts/{context_id}")
    assert detail.status_code == 200
    assert [item["text"] for item in detail.json()["messages"]] == [
        "貨到了嗎？",
        "還沒",
        "廠商說星期四到",
    ]
    assert [item["sequence"] for item in detail.json()["messages"]] == [1, 2, 3]

    finalizer = ContextFinalizer(database.session_factory, buffer_seconds=180)
    job_ids = finalizer.finalize_due(now=base + timedelta(minutes=6))
    assert len(job_ids) == 1
    with database.session_factory() as session:
        context = session.get(Context, context_id)
        assert context is not None and context.status == ContextStatus.READY.value
        analysis_job = session.get(ProcessingJob, job_ids[0])
        assert analysis_job is not None and analysis_job.job_type == "analyze_context"


def test_message_after_window_starts_new_context(test_context) -> None:
    client, database, queue = test_context
    base = datetime.now(UTC).replace(microsecond=0)
    _post(
        client,
        _payload("event-window-1", "message-window-1", "第一個主題", int(base.timestamp() * 1000)),
    )
    _post(
        client,
        _payload(
            "event-window-2",
            "message-window-2",
            "十六分鐘後的新主題",
            int((base + timedelta(minutes=16)).timestamp() * 1000),
        ),
    )

    runner = _runner(database, queue)
    assert runner.process_once(timeout_seconds=0) is True
    assert runner.process_once(timeout_seconds=0) is True

    with database.session_factory() as session:
        contexts = session.scalars(select(Context).order_by(Context.start_at)).all()
        assert len(contexts) == 2
        assert contexts[0].status == ContextStatus.READY.value
        assert contexts[1].status == ContextStatus.OPEN.value
        assert [context.message_count for context in contexts] == [1, 1]


def test_missing_context_returns_not_found(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/api/contexts/missing")

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "CONTEXT_NOT_FOUND"
