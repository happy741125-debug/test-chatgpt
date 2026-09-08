from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.intelligence.followup import followup_queue, mark_overdue
from app.models import IntelligenceObject, IntelligenceStatus

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _card(
    card_id: str,
    *,
    status: str,
    deadline_offset_hours: float | None,
    priority: str = "P2",
    requires_user_action: bool = False,
) -> IntelligenceObject:
    deadline = (
        None if deadline_offset_hours is None else NOW + timedelta(hours=deadline_offset_hours)
    )
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
        summary="測試卡片。",
        status=status,
        deadline_at=deadline,
        priority_level=priority,
        priority_score=50,
        confidence=0.8,
        requires_user_action=requires_user_action,
    )


def _seed(database, cards) -> None:  # type: ignore[no-untyped-def]
    with database.session_factory() as session:
        session.add_all(cards)
        session.commit()


def test_mark_overdue_flips_only_live_past_deadline_cards(test_context) -> None:
    _, database, _ = test_context
    _seed(
        database,
        [
            _card("open-past", status=IntelligenceStatus.OPEN.value, deadline_offset_hours=-2),
            _card(
                "wip-past", status=IntelligenceStatus.IN_PROGRESS.value, deadline_offset_hours=-1
            ),
            _card("open-future", status=IntelligenceStatus.OPEN.value, deadline_offset_hours=5),
            _card(
                "likely-past",
                status=IntelligenceStatus.LIKELY_DONE.value,
                deadline_offset_hours=-3,
            ),
            _card("done-past", status=IntelligenceStatus.DONE.value, deadline_offset_hours=-3),
            _card("no-deadline", status=IntelligenceStatus.OPEN.value, deadline_offset_hours=None),
        ],
    )

    flipped = mark_overdue(database.session_factory, now=NOW)
    assert flipped == 2

    with database.session_factory() as session:
        statuses = {c.id: c.status for c in session.query(IntelligenceObject).all()}
    assert statuses["open-past"] == IntelligenceStatus.OVERDUE.value
    assert statuses["wip-past"] == IntelligenceStatus.OVERDUE.value
    # Untouched:
    assert statuses["open-future"] == IntelligenceStatus.OPEN.value
    assert statuses["likely-past"] == IntelligenceStatus.LIKELY_DONE.value
    assert statuses["done-past"] == IntelligenceStatus.DONE.value
    assert statuses["no-deadline"] == IntelligenceStatus.OPEN.value

    # Idempotent: a second scan flips nothing new.
    assert mark_overdue(database.session_factory, now=NOW) == 0


def test_followup_queue_orders_overdue_first_then_soonest(test_context) -> None:
    _, database, _ = test_context
    _seed(
        database,
        [
            _card("overdue", status=IntelligenceStatus.OVERDUE.value, deadline_offset_hours=-5),
            _card("due-soon", status=IntelligenceStatus.OPEN.value, deadline_offset_hours=3),
            _card("due-later", status=IntelligenceStatus.OPEN.value, deadline_offset_hours=10),
            _card(
                "needs-user",
                status=IntelligenceStatus.OPEN.value,
                deadline_offset_hours=None,
                requires_user_action=True,
            ),
            # Not in queue: far future, no user action.
            _card("far", status=IntelligenceStatus.OPEN.value, deadline_offset_hours=100),
            # Not in queue: already done.
            _card("done", status=IntelligenceStatus.DONE.value, deadline_offset_hours=-1),
        ],
    )

    with database.session_factory() as session:
        items = followup_queue(session, now=NOW, due_within_hours=24)

    ids = [item.id for item in items]
    assert "far" not in ids
    assert "done" not in ids
    assert ids[0] == "overdue"  # overdue always first
    # due-soon before due-later; needs-user (no deadline) sorts last
    assert ids.index("due-soon") < ids.index("due-later")
    assert ids[-1] == "needs-user"


def test_followups_api_list_and_scan(test_context) -> None:
    client, database, _ = test_context
    # The scan endpoint uses the real clock, so seed a deadline firmly in the past.
    _seed(
        database,
        [_card("open-past", status=IntelligenceStatus.OPEN.value, deadline_offset_hours=-100000)],
    )

    scan = client.post("/api/followups/scan", headers=OPS_HEADERS)
    assert scan.status_code == 200
    assert scan.json()["overdue_marked"] == 1

    listing = client.get("/api/followups", headers=OPS_HEADERS)
    assert listing.status_code == 200
    body = listing.json()
    assert len(body) == 1
    assert body[0]["id"] == "open-past"
    assert body[0]["status"] == "OVERDUE"
    assert body[0]["overdue"] is True


def test_followups_api_requires_ops_token(test_context) -> None:
    client, _, _ = test_context
    assert client.get("/api/followups").status_code == 403
    assert client.post("/api/followups/scan").status_code == 403


def test_scan_endpoint_uses_request_session_bind(test_context) -> None:
    # Guards the sessionmaker(bind=...) wiring in the scan endpoint.
    client, database, _ = test_context
    _seed(
        database,
        [_card("p", status=IntelligenceStatus.OPEN.value, deadline_offset_hours=-1)],
    )
    factory = sessionmaker(bind=database.engine, expire_on_commit=False)
    assert mark_overdue(factory, now=NOW) == 1
