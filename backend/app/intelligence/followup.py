from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import IntelligenceObject, IntelligenceStatus

# Statuses that are still "live" and therefore eligible to become OVERDUE.
_OPEN_STATUSES = (
    IntelligenceStatus.OPEN.value,
    IntelligenceStatus.IN_PROGRESS.value,
    IntelligenceStatus.WAITING.value,
)
# A card counts as needing follow-up while it is live or already overdue.
_ATTENTION_STATUSES = (*_OPEN_STATUSES, IntelligenceStatus.OVERDUE.value)


def mark_overdue(session_factory: sessionmaker[Session], *, now: datetime | None = None) -> int:
    """Flip live cards whose deadline has passed to OVERDUE. Idempotent."""
    moment = _as_utc(now or datetime.now(UTC))
    flipped = 0
    with session_factory() as session:
        cards = session.scalars(
            select(IntelligenceObject).where(
                IntelligenceObject.deadline_at.is_not(None),
                IntelligenceObject.status.in_(_OPEN_STATUSES),
            )
        ).all()
        for card in cards:
            if card.deadline_at is not None and _as_utc(card.deadline_at) < moment:
                card.status = IntelligenceStatus.OVERDUE.value
                flipped += 1
        if flipped:
            session.commit()
    return flipped


@dataclass(frozen=True)
class FollowupItem:
    id: str
    title: str
    status: str
    priority_level: str
    domain_code: str
    owner_text: str | None
    deadline_at: datetime | None
    requires_user_action: bool
    overdue: bool


def followup_queue(
    session: Session, *, now: datetime | None = None, due_within_hours: int = 24
) -> list[FollowupItem]:
    """Cards that still need attention, most urgent first.

    Includes anything overdue, due within the horizon, or explicitly needing the
    user. Ordering: overdue first, then by soonest deadline (undated last),
    then by priority.
    """
    moment = _as_utc(now or datetime.now(UTC))
    horizon_seconds = due_within_hours * 3600
    cards = session.scalars(
        select(IntelligenceObject).where(
            IntelligenceObject.status.in_(_ATTENTION_STATUSES)
        )
    ).all()

    items: list[FollowupItem] = []
    for card in cards:
        overdue = card.status == IntelligenceStatus.OVERDUE.value or (
            card.deadline_at is not None and _as_utc(card.deadline_at) < moment
        )
        due_soon = (
            card.deadline_at is not None
            and 0 <= (_as_utc(card.deadline_at) - moment).total_seconds() <= horizon_seconds
        )
        if not (overdue or due_soon or card.requires_user_action):
            continue
        items.append(
            FollowupItem(
                id=card.id,
                title=card.title,
                status=card.status,
                priority_level=card.priority_level,
                domain_code=card.domain_code,
                owner_text=card.owner_text,
                deadline_at=card.deadline_at,
                requires_user_action=card.requires_user_action,
                overdue=overdue,
            )
        )

    items.sort(key=_sort_key)
    return items


def _sort_key(item: FollowupItem) -> tuple[int, float, int]:
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(item.priority_level, 9)
    if item.deadline_at is None:
        deadline_rank = float("inf")
    else:
        deadline_rank = _as_utc(item.deadline_at).timestamp()
    return (0 if item.overdue else 1, deadline_rank, priority_rank)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
