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

    def add(card: IntelligenceObject, event_type: str, occurred_at, evidence, actor: str) -> None:
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
                snapshot_json=build_snapshot(card),
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
            )

    return created
