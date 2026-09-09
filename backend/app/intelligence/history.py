from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import IntelligenceHistoryEvent, IntelligenceObject

# Lifecycle event types recorded to the append-only history.
NEW = "NEW"
UPDATED = "UPDATED"
DETERIORATED = "DETERIORATED"
RESCHEDULED = "RESCHEDULED"
LIKELY_DONE = "LIKELY_DONE"
DONE = "DONE"
REOPENED = "REOPENED"
CANCELLED = "CANCELLED"
RECURRED = "RECURRED"
MANUAL_CORRECTION = "MANUAL_CORRECTION"


def build_snapshot(card: IntelligenceObject) -> dict[str, object]:
    """Capture the case state at the moment an event happens (raw; redact on read)."""
    return {
        "title": card.title,
        "summary": card.summary,
        "status": card.status,
        "domain_code": card.domain_code,
        "priority_level": card.priority_level,
        "attention_level": card.attention_level,
        "requires_user_action": card.requires_user_action,
        "owner_text": card.owner_text,
        "deadline_at": card.deadline_at.isoformat() if card.deadline_at else None,
        "lifecycle_stage": card.lifecycle_stage,
        "blocker_type": card.blocker_type,
    }


def record_event(
    session: Session,
    card: IntelligenceObject,
    event_type: str,
    *,
    occurred_at: datetime | None = None,
    actor_text: str = "SYSTEM",
    evidence_message_ids: Iterable[str] | None = None,
) -> IntelligenceHistoryEvent:
    """Append one immutable lifecycle event. Never updates or deletes."""
    event = IntelligenceHistoryEvent(
        intelligence_id=card.id,
        event_type=event_type,
        occurred_at=occurred_at or datetime.now(UTC),
        actor_text=actor_text,
        evidence_message_ids_json=list(evidence_message_ids or []),
        snapshot_json=build_snapshot(card),
    )
    session.add(event)
    return event
