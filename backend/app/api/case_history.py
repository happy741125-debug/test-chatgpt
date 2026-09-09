from __future__ import annotations

import base64
import binascii
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import (
    IntelligenceHistoryEvent,
    IntelligenceObject,
    IntelligenceSource,
    Message,
)
from app.security.redaction import redact_sensitive_text

router = APIRouter(prefix="/api", tags=["case-history"])
TAIPEI = ZoneInfo("Asia/Taipei")
_DEFAULT_WINDOW_DAYS = 30
_DONE_EVENTS = ("DONE",)
_ACTIVE_STATUSES = ("OPEN", "IN_PROGRESS", "WAITING", "OVERDUE")


class CaseHistoryItem(BaseModel):
    id: str
    title: str
    summary: str
    domain_code: str
    priority_level: str
    attention_level: str
    status: str
    change_kind: str
    owner_text: str | None
    deadline_at: datetime | None
    created_at: datetime
    last_changed_at: datetime
    completed_at: datetime | None = None
    completed_by: str | None = None
    source_platforms: list[str] = Field(default_factory=list)


class CaseHistoryPage(BaseModel):
    items: list[CaseHistoryItem]
    next_cursor: str | None = None
    has_more: bool = False


class HistoryEventResponse(BaseModel):
    id: str
    event_type: str
    occurred_at: datetime
    actor_text: str
    evidence_message_ids: list[str]
    snapshot: dict[str, object]


def _encode_cursor(changed_at: datetime, card_id: str) -> str:
    aware = changed_at if changed_at.tzinfo else changed_at.replace(tzinfo=UTC)
    raw = f"{aware.isoformat()}|{card_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        iso, card_id = raw.split("|", 1)
        return datetime.fromisoformat(iso), card_id
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_CURSOR"},
        ) from exc


@router.get("/intelligence/history")
def case_history(
    _: OpsAccess,
    session: SessionDependency,
    date_from: date | None = None,
    date_to: date | None = None,
    card_status: str | None = Query(default=None, alias="status"),
    domain: str | None = None,
    priority: Literal["P0", "P1", "P2", "P3"] | None = None,
    platform: Literal["LINE", "GMAIL"] | None = None,
    change_kind: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> CaseHistoryPage:
    today = datetime.now(TAIPEI).date()
    start_date = date_from or (today - timedelta(days=_DEFAULT_WINDOW_DAYS))
    end_date = date_to or today
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_DATE_RANGE"},
        )
    window_start = datetime.combine(start_date, time.min, TAIPEI).astimezone(UTC)
    window_end = datetime.combine(end_date + timedelta(days=1), time.min, TAIPEI).astimezone(UTC)

    query = select(IntelligenceObject)
    if change_kind:
        matching_event = (
            select(IntelligenceHistoryEvent.id)
            .where(
                IntelligenceHistoryEvent.intelligence_id == IntelligenceObject.id,
                IntelligenceHistoryEvent.event_type == change_kind,
                IntelligenceHistoryEvent.occurred_at >= window_start,
                IntelligenceHistoryEvent.occurred_at < window_end,
            )
            .exists()
        )
        query = query.where(matching_event)
    else:
        query = query.where(
            IntelligenceObject.last_changed_at >= window_start,
            IntelligenceObject.last_changed_at < window_end,
        )
    if card_status == "ACTIVE":
        query = query.where(IntelligenceObject.status.in_(_ACTIVE_STATUSES))
    elif card_status:
        query = query.where(IntelligenceObject.status == card_status)
    if domain:
        query = query.where(IntelligenceObject.domain_code == domain)
    if priority:
        query = query.where(IntelligenceObject.priority_level == priority)
    if q:
        like = f"%{q}%"
        query = query.where(
            IntelligenceObject.title.ilike(like) | IntelligenceObject.summary.ilike(like)
        )
    if platform:
        query = query.where(
            IntelligenceObject.id.in_(
                select(IntelligenceSource.intelligence_id)
                .join(Message, Message.id == IntelligenceSource.message_id)
                .where(Message.platform == platform)
            )
        )
    if cursor:
        cur_changed, cur_id = _decode_cursor(cursor)
        query = query.where(
            (IntelligenceObject.last_changed_at < cur_changed)
            | (
                (IntelligenceObject.last_changed_at == cur_changed)
                & (IntelligenceObject.id < cur_id)
            )
        )
    cards = session.scalars(
        query.order_by(
            IntelligenceObject.last_changed_at.desc(), IntelligenceObject.id.desc()
        ).limit(limit + 1)
    ).all()

    has_more = len(cards) > limit
    page = cards[:limit]
    completions = _completion_map(session, [card.id for card in page])
    platforms = _platform_map(session, [card.id for card in page])
    items = [
        CaseHistoryItem(
            id=card.id,
            title=redact_sensitive_text(card.title) or "（內容已遮蔽）",
            summary=redact_sensitive_text(card.summary) or "（內容已遮蔽）",
            domain_code=card.domain_code,
            priority_level=card.priority_level,
            attention_level=card.attention_level,
            status=card.status,
            change_kind=card.change_kind,
            owner_text=redact_sensitive_text(card.owner_text),
            deadline_at=card.deadline_at,
            created_at=card.created_at,
            last_changed_at=card.last_changed_at,
            completed_at=(
                completions.get(card.id, (None, None))[0]
                if card.status in {"DONE", "ARCHIVED"}
                else None
            ),
            completed_by=(
                completions.get(card.id, (None, None))[1]
                if card.status in {"DONE", "ARCHIVED"}
                else None
            ),
            source_platforms=platforms.get(card.id, []),
        )
        for card in page
    ]
    next_cursor = (
        _encode_cursor(page[-1].last_changed_at, page[-1].id) if has_more and page else None
    )
    return CaseHistoryPage(items=items, next_cursor=next_cursor, has_more=has_more)


@router.get("/intelligence/{intelligence_id}/history")
def case_event_history(
    intelligence_id: str,
    _: OpsAccess,
    session: SessionDependency,
) -> list[HistoryEventResponse]:
    card = session.get(IntelligenceObject, intelligence_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "INTELLIGENCE_NOT_FOUND"},
        )
    events = session.scalars(
        select(IntelligenceHistoryEvent)
        .where(IntelligenceHistoryEvent.intelligence_id == intelligence_id)
        .order_by(IntelligenceHistoryEvent.occurred_at, IntelligenceHistoryEvent.id)
    ).all()
    return [
        HistoryEventResponse(
            id=event.id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            actor_text=event.actor_text,
            evidence_message_ids=event.evidence_message_ids_json,
            snapshot=_redact_snapshot(event.snapshot_json),
        )
        for event in events
    ]


def _redact_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    redacted = dict(snapshot)
    for key in ("title", "summary", "owner_text"):
        if redacted.get(key):
            redacted[key] = redact_sensitive_text(str(redacted[key]))
    return redacted


def _completion_map(
    session, card_ids: list[str]
) -> dict[str, tuple[datetime | None, str | None]]:  # type: ignore[no-untyped-def]
    if not card_ids:
        return {}
    rows = session.scalars(
        select(IntelligenceHistoryEvent)
        .where(
            IntelligenceHistoryEvent.intelligence_id.in_(card_ids),
            IntelligenceHistoryEvent.event_type.in_(_DONE_EVENTS),
        )
        .order_by(IntelligenceHistoryEvent.occurred_at)
    ).all()
    result: dict[str, tuple[datetime | None, str | None]] = {}
    for event in rows:
        actor = event.actor_text if event.actor_text and event.actor_text != "SYSTEM" else None
        result[event.intelligence_id] = (event.occurred_at, actor)
    return result


def _platform_map(session, card_ids: list[str]) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    if not card_ids:
        return {}
    rows = session.execute(
        select(IntelligenceSource.intelligence_id, Message.platform)
        .join(Message, Message.id == IntelligenceSource.message_id)
        .where(IntelligenceSource.intelligence_id.in_(card_ids))
        .distinct()
    ).all()
    grouped: dict[str, list[str]] = {}
    for card_id, plat in rows:
        grouped.setdefault(card_id, [])
        if plat not in grouped[card_id]:
            grouped[card_id].append(plat)
    for card_id in grouped:
        grouped[card_id].sort()
    return grouped
