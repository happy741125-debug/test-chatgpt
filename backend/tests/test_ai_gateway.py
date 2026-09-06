from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.ai.gateway import AIGateway, AIGatewayError, AIOutputValidationError
from app.ai.providers import MockAIProvider
from app.line.security import make_signature
from app.models import (
    AIRun,
    AIRunStatus,
    Context,
    ContextStatus,
    Message,
    ProcessingStatus,
    PromptStatus,
    PromptVersion,
)
from app.services.context import ContextFinalizer
from app.worker import ContextPipelineHandler, JobRunner

SECRET = "test-channel-secret"


def _create_ready_context(client, database, queue) -> tuple[str, str]:
    created_at = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "events": [
            {
                "type": "message",
                "timestamp": int(created_at.timestamp() * 1000),
                "source": {"type": "group", "groupId": "C-ai", "userId": "U-ai"},
                "webhookEventId": "event-ai-1",
                "message": {
                    "id": "message-ai-1",
                    "type": "text",
                    "text": "A 客戶缺貨 20 箱，Kevin 已補貨，明天下午到。",
                },
            }
        ]
    }
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
    pipeline = ContextPipelineHandler(
        database.session_factory,
        queue,
        window_minutes=15,
        max_messages=30,
        buffer_seconds=180,
    )
    runner = JobRunner(database.session_factory, queue, pipeline, retry_base_seconds=0)
    assert runner.process_once(timeout_seconds=0) is True
    finalizer = ContextFinalizer(database.session_factory, buffer_seconds=180)
    job_ids = finalizer.finalize_due(now=created_at + timedelta(minutes=5))
    assert len(job_ids) == 1
    with database.session_factory() as session:
        context = session.scalar(select(Context))
        message = session.scalar(select(Message))
        assert context is not None and message is not None
        session.add(
            PromptVersion(
                name="context-intelligence",
                version=1,
                template_text="Return structured operational intelligence.",
                output_schema_version="v1",
                status=PromptStatus.ACTIVE.value,
                activated_at=datetime.now(UTC),
            )
        )
        session.commit()
        return context.id, message.id


def _valid_output(message_id: str, *, confidence: float = 0.94) -> dict[str, object]:
    return {
        "work_related": True,
        "noise_type": None,
        "summary": "A 客戶缺貨 20 箱，已安排補貨。",
        "entities": [
            {
                "type": "CUSTOMER",
                "text": "A 客戶",
                "evidence_message_id": message_id,
                "confidence": 0.93,
            }
        ],
        "items": [
            {
                "type": "RISK",
                "domain_code": "WAREHOUSE_OPERATIONS",
                "event_type_code": "STOCK_SHORTAGE",
                "title": "A 客戶缺貨 20 箱",
                "summary": "Kevin 已補貨，預計明天下午到。",
                "owner_text": "Kevin",
                "deadline": {
                    "raw_text": "明天下午",
                    "resolved_at": None,
                    "timezone": "Asia/Taipei",
                    "confidence": 0.8,
                },
                "requires_user_action": False,
                "evidence_message_ids": [message_id],
                "confidence": confidence,
            }
        ],
        "overall_confidence": confidence,
    }


def test_mock_gateway_validates_and_persists_success(test_context) -> None:
    client, database, queue = test_context
    context_id, message_id = _create_ready_context(client, database, queue)
    provider = MockAIProvider(_valid_output(message_id))
    gateway = AIGateway(database.session_factory, provider)

    output = gateway.analyze_context(context_id)

    assert output.work_related is True
    assert len(provider.requests) == 1
    assert provider.requests[0].timezone == "Asia/Taipei"
    assert provider.requests[0].reference_time.endswith("+08:00")
    assert provider.requests[0].messages[0].id == message_id
    with database.session_factory() as session:
        run = session.scalar(select(AIRun))
        context = session.get(Context, context_id)
        message = session.get(Message, message_id)
        assert run is not None and run.status == AIRunStatus.SUCCEEDED.value
        assert run.provider == "mock" and run.estimated_cost_microunits == 0
        assert run.validated_output_json is not None
        assert run.requires_review is False
        assert context is not None and context.status == ContextStatus.ANALYZED.value
        assert message is not None
        assert message.processing_status == ProcessingStatus.PROCESSED.value


def test_low_confidence_output_is_routed_for_review(test_context) -> None:
    client, database, queue = test_context
    context_id, message_id = _create_ready_context(client, database, queue)
    gateway = AIGateway(
        database.session_factory,
        MockAIProvider(_valid_output(message_id, confidence=0.6)),
    )

    gateway.analyze_context(context_id)

    with database.session_factory() as session:
        run = session.scalar(select(AIRun))
        assert run is not None and run.requires_review is True


def test_invalid_evidence_fails_without_becoming_analyzed(test_context) -> None:
    client, database, queue = test_context
    context_id, message_id = _create_ready_context(client, database, queue)
    output = _valid_output(message_id)
    output["items"][0]["evidence_message_ids"] = ["outside-context"]  # type: ignore[index]
    gateway = AIGateway(database.session_factory, MockAIProvider(output))

    with pytest.raises(AIOutputValidationError):
        gateway.analyze_context(context_id)

    with database.session_factory() as session:
        run = session.scalar(select(AIRun))
        context = session.get(Context, context_id)
        assert run is not None and run.status == AIRunStatus.FAILED.value
        assert run.error_code == "AI_OUTPUT_VALIDATION_FAILED"
        assert context is not None and context.status == ContextStatus.FAILED.value


def test_provider_failure_is_recorded_without_exposing_input(test_context) -> None:
    client, database, queue = test_context
    context_id, _ = _create_ready_context(client, database, queue)

    def fail_provider(_request):  # type: ignore[no-untyped-def]
        raise TimeoutError("provider unavailable")

    gateway = AIGateway(database.session_factory, MockAIProvider(fail_provider))

    with pytest.raises(AIGatewayError):
        gateway.analyze_context(context_id)

    with database.session_factory() as session:
        run = session.scalar(select(AIRun))
        context = session.get(Context, context_id)
        assert run is not None and run.status == AIRunStatus.FAILED.value
        assert run.error_code == "AI_PROVIDER_ERROR"
        assert run.error_message == "AI analysis failed; inspect the error code and stored run."
        assert context is not None and context.status == ContextStatus.FAILED.value


def test_context_pipeline_dispatches_analysis_handler(test_context) -> None:
    _, database, queue = test_context
    analyzed_context_ids: list[str] = []
    pipeline = ContextPipelineHandler(
        database.session_factory,
        queue,
        window_minutes=15,
        max_messages=30,
        buffer_seconds=180,
        analysis_handler=analyzed_context_ids.append,
    )

    pipeline("analyze_context", {"context_id": "context-1"})

    assert analyzed_context_ids == ["context-1"]
