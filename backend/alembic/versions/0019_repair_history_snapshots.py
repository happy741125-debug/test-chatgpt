"""Repair reconstructed history snapshots used by V3.4.

Revision ID: 0019_repair_history_snapshots
Revises: 0018_intelligence_history
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from alembic import op

revision: str = "0019_repair_history_snapshots"
down_revision: str | None = "0018_intelligence_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def upgrade() -> None:
    from app.models import IntelligenceHistoryEvent, IntelligenceObject

    session = Session(bind=op.get_bind())
    try:
        cards = {
            card.id: card for card in session.scalars(select(IntelligenceObject)).all()
        }
        for event in session.scalars(select(IntelligenceHistoryEvent)).all():
            card = cards.get(event.intelligence_id)
            snapshot = dict(event.snapshot_json or {})
            changed = False
            known_status = _EVENT_STATUSES.get(event.event_type)
            if known_status and snapshot.get("status") != known_status:
                snapshot["status"] = known_status
                changed = True
            if "requires_user_action" not in snapshot and card is not None:
                snapshot["requires_user_action"] = card.requires_user_action
                changed = True
            if changed:
                event.snapshot_json = snapshot
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    # This migration corrects historical display metadata. Reverting would
    # intentionally restore known-wrong snapshots, so no data downgrade occurs.
    pass
