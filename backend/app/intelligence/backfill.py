from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.history import build_snapshot
from app.models import (
    IntelligenceChangeAudit,
    IntelligenceHistoryEvent,
    IntelligenceObject,
    IntelligenceStatusAudit,
)

_STATUS_ACTION_EVENTS = {
    "CONFIRM_DONE": "DONE",
    "REOPENED": "REOPENED",
    "AUTO_LIKELY_DONE": "LIKELY_DONE",
}

_EVENT_STATUSES = {
    "NEW": "OPEN",
    "UPDATED": "IN_PROGRESS",
    "DETERIORATED": "IN_PROGRESS",
    "RESCHEDULED": "IN_PROGRESS",
    "RECURRED": "IN_PROGRESS",
    "LIKELY_DONE": "LIKELY_DONE",
    "DONE": "DONE",
    "REOPENED": "IN_PROGRESS",
    "CANCELLED": "CANCELLED",
}


def _historical_snapshot(
    card: IntelligenceObject,
    event_type: str,
    *,
    status_override: str | None = None,
    lifecycle_stage: str | None = None,
    blocker_type: str | None = None,
) -> dict[str, object]:
    """Build the best reconstructable historical state for legacy events.

    Old audit rows do not contain full card snapshots.  Known lifecycle fields
    are applied explicitly instead of incorrectly presenting today's card state
    as the state at the time of a past event.
    """
    snapshot = build_snapshot(card)
    snapshot["status"] = status_override or _EVENT_STATUSES.get(
        event_type, snapshot["status"]
    )
    if lifecycle_stage is not None:
        snapshot["lifecycle_stage"] = lifecycle_stage
    if blocker_type is not None:
        snapshot["blocker_type"] = blocker_type
    return snapshot


def backfill_history_events(session: Session) -> int:
    """Seed the append-only history from existing cards and audit tables.

    Idempotent: an event keyed by (intelligence_id, event_type, occurred_at) is
    only inserted once, so re-running never duplicates.
    """
    existing: set[tuple[str, str, str]] = {
        (row.intelligence_id, row.event_type, row.occurred_at.isoformat())
        for row in session.scalars(select(IntelligenceHistoryEvent)).all()
    }
    cards = {card.id: card for card in session.scalars(select(IntelligenceObject)).all()}
    created = 0

    def add(
        card: IntelligenceObject,
        event_type: str,
        occurred_at,
        evidence,
        actor: str,
        *,
        status_override: str | None = None,
        lifecycle_stage: str | None = None,
        blocker_type: str | None = None,
    ) -> None:
        nonlocal created
        key = (card.id, event_type, occurred_at.isoformat())
        if key in existing:
            return
        existing.add(key)
        session.add(
            IntelligenceHistoryEvent(
                intelligence_id=card.id,
                event_type=event_type,
                occurred_at=occurred_at,
                actor_text=actor,
                evidence_message_ids_json=list(evidence or []),
                snapshot_json=_historical_snapshot(
                    card,
                    event_type,
                    status_override=status_override,
                    lifecycle_stage=lifecycle_stage,
                    blocker_type=blocker_type,
                ),
            )
        )
        created += 1

    # 1) A NEW event for every existing case, dated at its creation.
    for card in cards.values():
        add(card, "NEW", card.created_at, [], "SYSTEM")

    # 2) Existing change audits become change events.
    for audit in session.scalars(select(IntelligenceChangeAudit)).all():
        card = cards.get(audit.intelligence_id)
        if card is not None:
            add(
                card,
                audit.change_kind,
                audit.created_at,
                audit.evidence_message_ids_json,
                "SYSTEM",
                lifecycle_stage=audit.current_stage,
                blocker_type=audit.blocker_type,
            )

    # 3) Completion / reopen / auto-likely-done status audits become events.
    for audit in session.scalars(select(IntelligenceStatusAudit)).all():
        event_type = _STATUS_ACTION_EVENTS.get(audit.action)
        card = cards.get(audit.intelligence_id)
        if event_type and card is not None:
            add(
                card,
                event_type,
                audit.created_at,
                audit.evidence_message_ids_json,
                audit.actor_text,
                status_override=audit.to_status,
            )

    return created
