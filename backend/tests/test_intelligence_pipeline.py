from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.ai.gateway import AIGateway
from app.ai.providers import AnalysisMessage, AnalysisRequest, RuleBasedAIProvider
from app.ai.schemas import ContextAnalysisOutput
from app.intelligence.materializer import IntelligenceMaterializer, IntelligencePipeline
from app.intelligence.priority import calculate_priority
from app.line.security import make_signature
from app.models import (
    Context,
    Domain,
    EventType,
    IntelligenceObject,
    IntelligenceSource,
    Message,
    PromptStatus,
    PromptVersion,
)
from app.services.context import ContextFinalizer
from app.worker import ContextPipelineHandler, JobRunner

SECRET = "test-channel-secret"
OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _ready_context(test_context) -> tuple[object, object, object, str, str]:
    client, database, queue = test_context
    created_at = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "events": [
            {
                "type": "message",
                "timestamp": int(created_at.timestamp() * 1000),
                "source": {"type": "group", "groupId": "C-intel", "userId": "U-intel"},
                "webhookEventId": "event-intel-1",
                "message": {
                    "id": "message-intel-1",
                    "type": "text",
                    "text": "A客戶缺貨20箱，Kevin已請廠商補貨，預計明天下午到。",
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
    assert len(finalizer.finalize_due(now=created_at + timedelta(minutes=5))) == 1
    with database.session_factory() as session:
        context = session.scalar(select(Context))
        message = session.scalar(select(Message))
        assert context is not None and message is not None
        session.add_all(
            [
                PromptVersion(
                    name="context-intelligence",
                    version=1,
                    template_text="Return structured operational intelligence.",
                    output_schema_version="v1",
                    status=PromptStatus.ACTIVE.value,
                    activated_at=datetime.now(UTC),
                ),
                Domain(
                    code="WAREHOUSE_OPERATIONS",
                    name="倉儲營運",
                    description="倉儲營運",
                ),
                EventType(
                    code="STOCK_SHORTAGE",
                    domain_code="WAREHOUSE_OPERATIONS",
                    name="庫存短缺",
                    description="庫存短缺",
                ),
                EventType(
                    code="REPLENISHMENT",
                    domain_code="WAREHOUSE_OPERATIONS",
                    name="補貨",
                    description="補貨",
                ),
                EventType(
                    code="OUTBOUND_OPERATION",
                    domain_code="WAREHOUSE_OPERATIONS",
                    name="出入庫作業",
                    description="出入庫作業",
                ),
            ]
        )
        session.commit()
        return client, database, queue, context.id, message.id


def test_rule_provider_creates_traceable_intelligence_cards(test_context) -> None:
    client, database, _, context_id, message_id = _ready_context(test_context)
    gateway = AIGateway(database.session_factory, RuleBasedAIProvider())
    materializer = IntelligenceMaterializer(database.session_factory)
    pipeline = IntelligencePipeline(gateway, materializer)

    intelligence_ids = pipeline(context_id)

    assert len(intelligence_ids) == 1
    with database.session_factory() as session:
        cards = session.scalars(select(IntelligenceObject).order_by(IntelligenceObject.type)).all()
        assert len(cards) == 1
        assert cards[0].type == "EVENT"
        assert set(cards[0].facets_json) == {"EVENT", "TASK", "COMMITMENT", "RISK"}
        assert all(card.domain_code == "WAREHOUSE_OPERATIONS" for card in cards)
        # A next-afternoon shortage becomes P1 once it is less than 24 hours away.
        assert all(card.priority_level in {"P1", "P2"} for card in cards)
        # T5-15: P0/P1 cards below the high-confidence bar are routed to a human;
        # lower-priority cards are not flagged by this rule.
        assert all(
            card.requires_review == (card.priority_level in {"P0", "P1"}) for card in cards
        )
        sources = session.scalars(select(IntelligenceSource)).all()
        assert len(sources) == 1
        assert all(source.message_id == message_id for source in sources)

    output = gateway.analyze_context(context_id)
    repeated_ids = materializer.materialize(context_id, output)
    assert repeated_ids == intelligence_ids
    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(IntelligenceObject)) == 1

    today = client.get("/api/dashboard/today", headers=OPS_HEADERS)
    assert today.status_code == 200
    assert today.json()["total"] == 1
    assert len(today.json()["sections"]["risk"]) == 0
    assert len(today.json()["sections"]["follow_up"]) == 0
    assert len(today.json()["sections"]["team_handling"]) == 1
    assert len(today.json()["sections"]["fyi"]) == 0
    assert set(today.json()["sections"]["team_handling"][0]["facets"]) == {
        "EVENT",
        "TASK",
        "COMMITMENT",
        "RISK",
    }

    detail = client.get(f"/api/intelligence/{intelligence_ids[0]}", headers=OPS_HEADERS)
    assert detail.status_code == 200
    assert detail.json()["sources"][0]["message_id"] == message_id

    updated = client.patch(
        f"/api/intelligence/{intelligence_ids[0]}",
        headers=OPS_HEADERS,
        json={"status": "DONE"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "DONE"

    refreshed_today = client.get("/api/dashboard/today", headers=OPS_HEADERS)
    assert refreshed_today.status_code == 200
    assert refreshed_today.json()["total"] == 0


def test_rule_provider_classifies_general_chat_as_noise() -> None:
    request = AnalysisRequest(
        context_id="context-noise",
        context_version=1,
        timezone="Asia/Taipei",
        reference_time="2026-09-07T12:00:00+08:00",
        prompt_name="context-intelligence",
        prompt_version=1,
        prompt_template="Return schema v1.",
        messages=(
            AnalysisMessage(
                id="message-noise",
                sequence=1,
                sender_identity_id="identity-1",
                message_type="text",
                text="大家午安",
                source_created_at="2026-09-07T04:00:00+00:00",
            ),
        ),
    )

    response = RuleBasedAIProvider().analyze(request)
    output = ContextAnalysisOutput.model_validate(response.output)

    assert output.work_related is False
    assert output.noise_type == "GENERAL_CHAT"
    assert output.items == []
    assert response.estimated_cost_microunits == 0


def test_rule_provider_detects_customer_payment_follow_up() -> None:
    request = AnalysisRequest(
        context_id="context-payment",
        context_version=1,
        timezone="Asia/Taipei",
        reference_time="2026-09-08T12:00:00+08:00",
        prompt_name="context-intelligence",
        prompt_version=1,
        prompt_template="Return schema v1.",
        messages=(
            AnalysisMessage(
                id="message-payment",
                sequence=1,
                sender_identity_id="identity-1",
                message_type="text",
                text="請問 A 客戶是否已經匯款？目前帳上還沒看到入帳。",
                source_created_at="2026-09-08T04:00:00+00:00",
            ),
        ),
    )

    output = ContextAnalysisOutput.model_validate(RuleBasedAIProvider().analyze(request).output)

    assert output.work_related is True
    assert {item.event_type_code for item in output.items} == {"PAYMENT_STATUS"}
    assert {item.type.value for item in output.items} == {"EVENT", "RISK"}


def test_rule_provider_classifies_urgent_orders_with_order_ids_and_deadline() -> None:
    request = AnalysisRequest(
        context_id="context-urgent-order",
        context_version=1,
        timezone="Asia/Taipei",
        reference_time="2026-09-07T12:00:00+08:00",
        prompt_name="context-intelligence",
        prompt_version=1,
        prompt_template="Return schema v1.",
        messages=(
            AnalysisMessage(
                id="message-urgent-order-1",
                sequence=1,
                sender_identity_id="identity-1",
                message_type="text",
                text=("新增兩筆測試急單，明天務必安排出貨。\nORD-20991231-9001\nORD-20991231-9002"),
                source_created_at="2026-09-07T04:00:00+00:00",
            ),
            AnalysisMessage(
                id="message-urgent-order-2",
                sequence=2,
                sender_identity_id="identity-2",
                message_type="text",
                text="今天跟測試團隊確認並盡快安排",
                source_created_at="2026-09-07T04:01:00+00:00",
            ),
        ),
    )

    response = RuleBasedAIProvider().analyze(request)
    output = ContextAnalysisOutput.model_validate(response.output)

    assert output.work_related is True
    assert {item.type.value for item in output.items} == {"EVENT", "TASK", "COMMITMENT", "RISK"}
    assert all(item.event_type_code == "URGENT_ORDER" for item in output.items)
    assert all(item.deadline is not None for item in output.items)
    assert all(item.deadline.raw_text == "明天" for item in output.items if item.deadline)
    assert all(
        calculate_priority(item, now=datetime(2026, 9, 7, 4, tzinfo=UTC)).level == "P1"
        for item in output.items
    )
    event = next(item for item in output.items if item.type.value == "EVENT")
    assert "ORD-20991231-9001" in event.title
    assert "ORD-20991231-9002" in event.title
    assert response.estimated_cost_microunits == 0


def test_normal_outbound_update_is_not_misclassified_as_urgent() -> None:
    request = AnalysisRequest(
        context_id="context-normal-outbound",
        context_version=1,
        timezone="Asia/Taipei",
        reference_time="2026-09-07T12:00:00+08:00",
        prompt_name="context-intelligence",
        prompt_version=1,
        prompt_template="Return schema v1.",
        messages=(
            AnalysisMessage(
                id="message-normal-outbound",
                sequence=1,
                sender_identity_id="identity-1",
                message_type="text",
                text="已入庫，訂單麻煩重新整理庫存，我們今日就會安排出貨。",
                source_created_at="2026-09-07T04:00:00+00:00",
            ),
        ),
    )

    output = ContextAnalysisOutput.model_validate(RuleBasedAIProvider().analyze(request).output)

    assert output.work_related is True
    assert {item.event_type_code for item in output.items} == {
        "INBOUND_OPERATION",
        "OUTBOUND_OPERATION",
    }
    assert all("急單" not in item.title for item in output.items)
    assert all(item.deadline is not None for item in output.items)
    assert all(item.deadline.raw_text == "今日" for item in output.items if item.deadline)


def test_priority_hard_rule_cannot_be_downgraded() -> None:
    output = ContextAnalysisOutput.model_validate(
        {
            "work_related": True,
            "noise_type": None,
            "summary": "WMS 全面故障。",
            "entities": [],
            "items": [
                {
                    "type": "RISK",
                    "domain_code": "SYSTEM",
                    "event_type_code": "SYSTEM_INCIDENT",
                    "title": "WMS 全面故障",
                    "summary": "所有出貨暫停。",
                    "owner_text": None,
                    "deadline": None,
                    "requires_user_action": False,
                    "evidence_message_ids": ["message-1"],
                    "confidence": 0.9,
                }
            ],
            "overall_confidence": 0.9,
        }
    )

    priority = calculate_priority(output.items[0])

    assert priority.level == "P0"
    assert priority.score >= 80
    assert any(reason["code"] == "CRITICAL_HARD_RULE" for reason in priority.reasons)
