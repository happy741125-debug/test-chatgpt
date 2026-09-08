from __future__ import annotations

from datetime import UTC, datetime

from app.intelligence.attention import classify_attention
from app.intelligence.completion import has_completion_evidence, mark_likely_done_from_messages
from app.models import IntelligenceObject, IntelligenceStatus, IntelligenceStatusAudit, Message

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _card(card_id: str, *, attention_level: str = "TEAM") -> IntelligenceObject:
    return IntelligenceObject(
        id=card_id,
        case_key=f"case-{card_id}",
        facets_json=["TASK"],
        context_id=f"ctx-{card_id}",
        context_version=1,
        ai_run_id=f"run-{card_id}",
        fingerprint=f"fp-{card_id}",
        type="TASK",
        domain_code="WAREHOUSE_OPERATIONS",
        event_type_code="URGENT_ORDER",
        title=f"任務 {card_id}",
        summary="去識別化測試卡片。",
        status=IntelligenceStatus.IN_PROGRESS.value,
        priority_level="P2",
        priority_score=50,
        confidence=0.8,
        requires_user_action=False,
        attention_level=attention_level,
        attention_reasons_json=["TEAM_DEFAULT"],
        created_at=datetime(2026, 9, 8, 4, 0, tzinfo=UTC),
    )


def _message(message_id: str, text: str) -> Message:
    return Message(
        id=message_id,
        platform="LINE",
        external_message_id=f"external-{message_id}",
        raw_event_id=f"event-{message_id}",
        channel_id="channel-test",
        conversation_id="conversation-test",
        message_type="text",
        text=text,
        source_created_at=datetime(2026, 9, 8, 4, 5, tzinfo=UTC),
    )


def test_attention_routing_is_conservative() -> None:
    team = classify_attention(facets=["TASK"], priority_level="P2", requires_user_action=False)
    boss = classify_attention(
        facets=["DECISION_REQUIRED"], priority_level="P1", requires_user_action=True
    )
    assert team.level == "TEAM"
    assert boss.level == "BOSS"
    assert "REQUIRES_OWNER_ACTION" in boss.reasons
    assert classify_attention(
        facets=["FYI"], priority_level="P3", requires_user_action=False
    ).level != "NOISE"


def test_completion_evidence_avoids_questions_and_negation() -> None:
    assert has_completion_evidence("這筆已經出貨，謝謝") is True
    assert has_completion_evidence("問題已解決，可以結案") is True
    assert has_completion_evidence("請問是否已出貨？") is False
    assert has_completion_evidence("這筆還沒出貨") is False
    assert has_completion_evidence("入庫了嗎？") is False


def test_completion_evidence_marks_likely_done_and_writes_audit(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        card = _card("completion")
        done_message = _message("message-done", "已處理完成，謝謝")
        session.add_all([card, done_message])
        session.commit()

        evidence = mark_likely_done_from_messages(session, card, [done_message.id])
        session.commit()

        audit = session.query(IntelligenceStatusAudit).one()
        assert evidence == [done_message.id]
        assert card.status == IntelligenceStatus.LIKELY_DONE.value
        assert audit.action == "AUTO_LIKELY_DONE"
        assert audit.evidence_message_ids_json == [done_message.id]


def test_manual_done_reopened_and_history_api(test_context) -> None:
    client, database, _ = test_context
    with database.session_factory() as session:
        card = _card("manual")
        card.status = IntelligenceStatus.LIKELY_DONE.value
        session.add(card)
        session.commit()

    done = client.post(
        "/api/intelligence/manual/status-actions",
        headers=OPS_HEADERS,
        json={"action": "CONFIRM_DONE", "actor_text": "測試主管"},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "DONE"

    reopened = client.post(
        "/api/intelligence/manual/status-actions",
        headers=OPS_HEADERS,
        json={"action": "REOPENED", "actor_text": "測試主管", "note": "仍需補件"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "IN_PROGRESS"

    history = client.get("/api/intelligence/manual/status-history", headers=OPS_HEADERS)
    assert history.status_code == 200
    assert [entry["action"] for entry in history.json()] == ["CONFIRM_DONE", "REOPENED"]
    assert history.json()[1]["note"] == "仍需補件"

    invalid = client.post(
        "/api/intelligence/manual/status-actions",
        headers=OPS_HEADERS,
        json={"action": "REOPENED", "actor_text": "測試主管"},
    )
    assert invalid.status_code == 409


def test_team_daily_digest_excludes_boss_and_noise(test_context) -> None:
    client, database, _ = test_context
    with database.session_factory() as session:
        session.add_all(
            [
                _card("team", attention_level="TEAM"),
                _card("boss", attention_level="BOSS"),
                _card("noise", attention_level="NOISE"),
            ]
        )
        session.commit()

    response = client.get(
        "/api/digests/team/daily?date=2026-09-08",
        headers=OPS_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [card["id"] for card in body["cards"]] == ["team"]
    assert body["by_priority"] == {"P2": 1}
