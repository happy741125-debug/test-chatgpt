from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.ai.schemas import ContextAnalysisOutput
from app.intelligence.backfill import backfill_history_events
from app.intelligence.history import record_event
from app.intelligence.materializer import IntelligenceMaterializer
from app.models import (
    AIRun,
    AIRunStatus,
    Context,
    IntelligenceChangeAudit,
    IntelligenceHistoryEvent,
    IntelligenceObject,
    Message,
    Platform,
)

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _seed_context(database, message_text: str) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    now = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
    with database.session_factory() as session:
        session.add_all(
            [
                Context(
                    id="ctx-h1",
                    channel_id="ch-h1",
                    start_at=now,
                    end_at=now + timedelta(minutes=5),
                    version=1,
                ),
                AIRun(
                    id="run-h1",
                    context_id="ctx-h1",
                    context_version=1,
                    prompt_version_id="pv-h1",
                    provider="rule-based",
                    model="test",
                    status=AIRunStatus.SUCCEEDED.value,
                    requires_review=False,
                ),
                Message(
                    id="msg-h1",
                    platform=Platform.LINE.value,
                    external_message_id="ext-h1",
                    raw_event_id="raw-h1",
                    channel_id="ch-h1",
                    conversation_id="conv-h1",
                    message_type="text",
                    text=message_text,
                    source_created_at=now,
                ),
            ]
        )
        session.commit()
    return "ctx-h1", "msg-h1"


def _output(evidence_id: str) -> ContextAnalysisOutput:
    return ContextAnalysisOutput.model_validate(
        {
            "work_related": True,
            "noise_type": None,
            "summary": "缺貨案件測試摘要。",
            "entities": [],
            "items": [
                {
                    "type": "EVENT",
                    "domain_code": "WAREHOUSE_OPERATIONS",
                    "event_type_code": "STOCK_SHORTAGE",
                    "title": "缺貨事件",
                    "summary": "測試事件。",
                    "owner_text": None,
                    "deadline": None,
                    "requires_user_action": False,
                    "evidence_message_ids": [evidence_id],
                    "confidence": 0.9,
                }
            ],
            "overall_confidence": 0.9,
        }
    )


def _materialize(database) -> str:  # type: ignore[no-untyped-def]
    ctx_id, msg_id = _seed_context(database, "有一批商品缺貨了")
    ids = IntelligenceMaterializer(database.session_factory).materialize(ctx_id, _output(msg_id))
    return ids[0]


def test_new_event_written_on_case_creation(test_context) -> None:
    _, database, _ = test_context
    card_id = _materialize(database)
    with database.session_factory() as session:
        events = session.scalars(
            select(IntelligenceHistoryEvent).where(
                IntelligenceHistoryEvent.intelligence_id == card_id
            )
        ).all()
    assert any(event.event_type == "NEW" for event in events)


def test_done_and_reopen_events_preserved(test_context) -> None:
    client, database, _ = test_context
    card_id = _materialize(database)

    done = client.post(
        f"/api/intelligence/{card_id}/status-actions",
        headers=OPS_HEADERS,
        json={"action": "CONFIRM_DONE", "actor_text": "Jacky"},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "DONE"

    reopen = client.post(
        f"/api/intelligence/{card_id}/status-actions",
        headers=OPS_HEADERS,
        json={"action": "REOPENED", "actor_text": "Jacky"},
    )
    assert reopen.status_code == 200

    history = client.get(f"/api/intelligence/{card_id}/history", headers=OPS_HEADERS).json()
    types = [event["event_type"] for event in history]
    assert types.count("NEW") == 1
    assert "DONE" in types and "REOPENED" in types
    # Append-only: DONE stays even after reopen.
    assert types.index("DONE") < types.index("REOPENED")

    reopened = client.get("/api/intelligence/history", headers=OPS_HEADERS).json()
    item = next(item for item in reopened["items"] if item["id"] == card_id)
    assert item["status"] == "IN_PROGRESS"
    assert item["completed_at"] is None
    assert item["completed_by"] is None


def test_case_history_includes_done_and_filters(test_context) -> None:
    client, database, _ = test_context
    card_id = _materialize(database)
    client.post(
        f"/api/intelligence/{card_id}/status-actions",
        headers=OPS_HEADERS,
        json={"action": "CONFIRM_DONE", "actor_text": "Jacky"},
    )

    done_only = client.get("/api/intelligence/history?status=DONE", headers=OPS_HEADERS).json()
    assert [item["id"] for item in done_only["items"]] == [card_id]
    assert done_only["items"][0]["completed_at"] is not None
    assert done_only["items"][0]["completed_by"] == "Jacky"

    # Filter that excludes the card returns nothing.
    other = client.get("/api/intelligence/history?priority=P0", headers=OPS_HEADERS).json()
    assert all(item["id"] != card_id for item in other["items"])

    # Platform filter matches the LINE source.
    line = client.get("/api/intelligence/history?platform=LINE", headers=OPS_HEADERS).json()
    assert any(item["id"] == card_id for item in line["items"])


def test_case_history_pagination_limits(test_context) -> None:
    client, database, _ = test_context
    now = datetime.now(UTC)
    with database.session_factory() as session:
        for i in range(3):
            card = IntelligenceObject(
                id=f"card-{i}",
                case_key=f"key-{i}",
                facets_json=["EVENT"],
                context_id="c",
                context_version=1,
                ai_run_id="r",
                fingerprint=f"fp-{i}",
                type="EVENT",
                domain_code="WAREHOUSE_OPERATIONS",
                event_type_code="STOCK_SHORTAGE",
                title=f"案件 {i}",
                summary="測試",
                confidence=0.8,
                last_changed_at=now - timedelta(minutes=i),
            )
            session.add(card)
        session.commit()

    first = client.get("/api/intelligence/history?limit=2", headers=OPS_HEADERS).json()
    assert len(first["items"]) == 2
    assert first["has_more"] is True and first["next_cursor"]
    second = client.get(
        f"/api/intelligence/history?limit=2&cursor={first['next_cursor']}", headers=OPS_HEADERS
    ).json()
    assert len(second["items"]) == 1
    ids = {item["id"] for item in first["items"]} | {item["id"] for item in second["items"]}
    assert ids == {"card-0", "card-1", "card-2"}


def test_case_history_change_filter_uses_immutable_events(test_context) -> None:
    client, database, _ = test_context
    card_id = _materialize(database)
    with database.session_factory() as session:
        card = session.get(IntelligenceObject, card_id)
        card.change_kind = "UPDATED"
        card.last_changed_at = datetime(2020, 1, 1, tzinfo=UTC)
        session.commit()

    today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    result = client.get(
        "/api/intelligence/history"
        f"?change_kind=NEW&date_from={today}&date_to={today}",
        headers=OPS_HEADERS,
    ).json()

    assert any(item["id"] == card_id for item in result["items"])


def test_case_history_active_status_and_invalid_date_range(test_context) -> None:
    client, database, _ = test_context
    card_id = _materialize(database)

    active = client.get("/api/intelligence/history?status=ACTIVE", headers=OPS_HEADERS)
    assert any(item["id"] == card_id for item in active.json()["items"])
    invalid = client.get(
        "/api/intelligence/history?date_from=2026-09-09&date_to=2026-09-08",
        headers=OPS_HEADERS,
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["error_code"] == "INVALID_DATE_RANGE"


def test_weekly_events_drilldown_and_frozen_snapshot(test_context) -> None:
    client, database, _ = test_context
    card_id = _materialize(database)  # writes a NEW event at 2026-09-08

    # The current week is "now"; place the drilldown query on this week.
    from app.api.weekly_reviews import _current_week

    week_start, week_end = _current_week()

    # Move the NEW event into the current week so it is counted.
    with database.session_factory() as session:
        event = session.scalar(
            select(IntelligenceHistoryEvent).where(
                IntelligenceHistoryEvent.intelligence_id == card_id,
                IntelligenceHistoryEvent.event_type == "NEW",
            )
        )
        event.occurred_at = datetime.now(UTC)
        session.commit()

    current = client.get("/api/weekly-reviews/current", headers=OPS_HEADERS).json()
    assert current["change_counts"].get("NEW", 0) >= 1

    events = client.get(
        f"/api/weekly-reviews/{week_end}/events?change_kind=NEW", headers=OPS_HEADERS
    ).json()
    assert any(item["intelligence_id"] == card_id for item in events["items"])
    assert events["settled"] is False

    # Close the review -> snapshot frozen.
    closed = client.patch(
        "/api/weekly-reviews/current", headers=OPS_HEADERS, json={"status": "CLOSED"}
    )
    assert closed.status_code == 200
    frozen_new = closed.json()["change_counts"].get("NEW", 0)
    assert frozen_new >= 1

    # Add another NEW event this week AFTER close; frozen numbers must not move.
    with database.session_factory() as session:
        card = session.get(IntelligenceObject, card_id)
        record_event(session, card, "NEW", occurred_at=datetime.now(UTC))
        session.commit()

    after = client.get(f"/api/weekly-reviews/{week_end}", headers=OPS_HEADERS).json()
    assert after["status"] == "CLOSED"
    assert after["change_counts"].get("NEW", 0) == frozen_new

    settled_events = client.get(
        f"/api/weekly-reviews/{week_end}/events?change_kind=NEW", headers=OPS_HEADERS
    ).json()
    assert settled_events["settled"] is True


def test_unsettled_historical_week_uses_event_snapshot_not_current_card(test_context) -> None:
    _, database, _ = test_context
    card_id = _materialize(database)
    from app.api.weekly_reviews import _live_counts

    with database.session_factory() as session:
        event = session.scalar(
            select(IntelligenceHistoryEvent).where(
                IntelligenceHistoryEvent.intelligence_id == card_id,
                IntelligenceHistoryEvent.event_type == "NEW",
            )
        )
        event.occurred_at = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)
        event.snapshot_json = {
            **event.snapshot_json,
            "status": "OPEN",
            "priority_level": "P1",
            "requires_user_action": True,
        }
        card = session.get(IntelligenceObject, card_id)
        card.last_changed_at = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)
        card.status = "DONE"
        card.priority_level = "P3"
        card.requires_user_action = False
        session.commit()

    with database.session_factory() as session:
        counts = _live_counts(
            session,
            datetime(2026, 8, 31).date(),
            datetime(2026, 9, 6).date(),
        )

    assert counts["total"] == 1
    assert counts["urgent"] == 1
    assert counts["decisions"] == 1


def test_future_week_rejected(test_context) -> None:
    client, _, _ = test_context
    from app.api.weekly_reviews import _current_week

    _, week_end = _current_week()
    future = (week_end + timedelta(days=7)).isoformat()
    assert client.get(f"/api/weekly-reviews/{future}", headers=OPS_HEADERS).status_code == 400


def test_backfill_is_idempotent(test_context) -> None:
    _, database, _ = test_context
    now = datetime.now(UTC)
    with database.session_factory() as session:
        session.add(
            IntelligenceObject(
                id="legacy-1",
                case_key="legacy-key",
                facets_json=["EVENT"],
                context_id="c",
                context_version=1,
                ai_run_id="r",
                fingerprint="fp-legacy",
                type="EVENT",
                domain_code="WAREHOUSE_OPERATIONS",
                event_type_code="STOCK_SHORTAGE",
                title="舊案件",
                summary="測試",
                status="DONE",
                confidence=0.8,
                requires_user_action=True,
                created_at=now,
                last_changed_at=now,
            )
        )
        session.add(
            IntelligenceChangeAudit(
                intelligence_id="legacy-1",
                change_kind="UPDATED",
                evidence_message_ids_json=[],
                created_at=now + timedelta(minutes=1),
            )
        )
        session.commit()

    with database.session_factory() as session:
        first = backfill_history_events(session)
        session.commit()
    with database.session_factory() as session:
        second = backfill_history_events(session)
        session.commit()
    assert first == 2  # NEW + UPDATED
    assert second == 0  # idempotent

    with database.session_factory() as session:
        events = session.scalars(
            select(IntelligenceHistoryEvent).where(
                IntelligenceHistoryEvent.intelligence_id == "legacy-1"
            )
        ).all()
    assert sorted(event.event_type for event in events) == ["NEW", "UPDATED"]
    new_event = next(event for event in events if event.event_type == "NEW")
    assert new_event.snapshot_json["status"] == "OPEN"
    assert new_event.snapshot_json["requires_user_action"] is True


def test_history_endpoints_require_ops_token(test_context) -> None:
    client, _, _ = test_context
    assert client.get("/api/intelligence/history").status_code == 403
    assert client.get("/api/weekly-reviews").status_code == 403
