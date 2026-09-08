from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.intelligence.completion import has_completion_evidence, mark_likely_done_from_messages
from app.intelligence.signals import classify_operational_signal, detect_blocker
from app.models import IntelligenceFeedback, IntelligenceObject, Message

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _card(card_id: str, event_type: str, *, status: str = "IN_PROGRESS") -> IntelligenceObject:
    return IntelligenceObject(
        id=card_id,
        case_key=f"case-{card_id}",
        facets_json=["EVENT"],
        context_id=f"ctx-{card_id}",
        context_version=1,
        ai_run_id=f"run-{card_id}",
        fingerprint=f"fp-{card_id}",
        type="EVENT",
        domain_code="WAREHOUSE_OPERATIONS",
        event_type_code=event_type,
        title="去識別化測試案件",
        summary="測試案件摘要",
        status=status,
        priority_level="P2",
        priority_score=40,
        confidence=0.85,
    )


def _message(message_id: str, text: str) -> Message:
    return Message(
        id=message_id,
        platform="LINE",
        external_message_id=f"external-{message_id}",
        raw_event_id=f"raw-{message_id}",
        channel_id="channel-test",
        conversation_id="conversation-test",
        message_type="text",
        text=text,
        source_created_at=datetime.now(UTC),
    )


def test_stage_completion_does_not_cross_operational_boundaries() -> None:
    assert has_completion_evidence("今日已入庫", "INBOUND_OPERATION") is True
    assert has_completion_evidence("今日已入庫", "URGENT_ORDER") is False
    assert has_completion_evidence("訂單已出貨", "URGENT_ORDER") is True
    assert has_completion_evidence("客戶表示已匯款", "PAYMENT_STATUS") is False
    assert has_completion_evidence("財務已確認入帳", "PAYMENT_STATUS") is True
    assert has_completion_evidence("系統已恢復正常", "SYSTEM_INCIDENT") is True


def test_blocker_and_change_kind_are_classified() -> None:
    assert detect_blocker("商品缺貨，目前調不到") == "STOCK"
    assert classify_operational_signal(
        "因缺貨無法出貨",
        event_type="URGENT_ORDER",
    ).change_kind == "DETERIORATED"
    assert classify_operational_signal(
        "已改期到下週",
        event_type="URGENT_ORDER",
    ).change_kind == "RESCHEDULED"
    cancelled = classify_operational_signal("這張已取消", event_type="DISPATCH_REQUEST")
    assert cancelled.change_kind == "CANCELLED"
    assert cancelled.completion is False


def test_completed_case_reopens_when_problem_recurs(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        card = _card("recurrence", "URGENT_ORDER", status="DONE")
        message = _message("recurrence-message", "同一商品又缺貨，目前仍調不到")
        session.add_all([card, message])
        session.commit()

        mark_likely_done_from_messages(session, card, [message.id])
        session.commit()

        assert card.status == "IN_PROGRESS"
        assert card.change_kind == "RECURRED"
        assert card.occurrence_count == 2


def test_attention_feedback_is_saved_as_learning_data(test_context) -> None:
    client, database, _ = test_context
    with database.session_factory() as session:
        session.add(_card("feedback", "URGENT_ORDER"))
        session.commit()

    response = client.post(
        "/api/intelligence/feedback/feedback",
        headers=OPS_HEADERS,
        json={"attention_level": "BOSS", "actor_text": "測試管理者"},
    )

    assert response.status_code == 200
    assert response.json()["fields_changed"] == ["attention_level"]
    with database.session_factory() as session:
        card = session.get(IntelligenceObject, "feedback")
        feedback = session.scalar(select(IntelligenceFeedback))
        assert card is not None and card.attention_level == "BOSS"
        assert card.attention_locked is True
        assert card.change_kind == "MANUAL_CORRECTION"
        assert feedback is not None and feedback.previous_value_json == "TEAM"
