from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.api.access import OpsAccess
from app.api.executive import DEFINITIONS_BY_CODE
from app.api.operational_performance import operational_review_signals
from app.api.revenue import revenue_review_signals
from app.dependencies import SessionDependency
from app.models import (
    ExecutiveMetricSnapshot,
    ImprovementAction,
    IntelligenceHistoryEvent,
    IntelligenceObject,
    IntelligenceStatus,
    WeeklyReview,
    WeeklyReviewSnapshot,
)
from app.security.redaction import redact_sensitive_text

router = APIRouter(prefix="/api/weekly-reviews", tags=["weekly-reviews"])
TAIPEI = ZoneInfo("Asia/Taipei")
OPEN_ACTION_STATUSES = ("OPEN", "IN_PROGRESS", "CARRY_OVER")
CLOSED_INTELLIGENCE_STATUSES = (
    IntelligenceStatus.DONE.value,
    IntelligenceStatus.CANCELLED.value,
    IntelligenceStatus.ARCHIVED.value,
)


class ReviewSignal(BaseModel):
    code: str
    label: str
    health_status: str
    current_value: float | None
    target_value: float | None
    unit: str
    note: str | None


class ImprovementActionResponse(BaseModel):
    id: str
    review_id: str
    review_week_end: date
    title: str
    issue_summary: str | None
    root_cause: str | None
    action_plan: str | None
    owner_name: str
    target_text: str | None
    result_text: str | None
    due_date: date | None
    status: str
    needs_jacky: bool
    created_at: datetime
    updated_at: datetime


class WeeklyReviewResponse(BaseModel):
    id: str | None
    week_start: date
    week_end: date
    status: str
    manager_name: str | None
    summary: str | None
    total_intelligence: int
    urgent_intelligence: int
    decisions_needed: int
    open_improvements: int
    change_counts: dict[str, int]
    metric_signals: list[ReviewSignal]
    actions: list[ImprovementActionResponse]


class WeeklyReviewUpdate(BaseModel):
    manager_name: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=2000)
    status: Literal["DRAFT", "IN_REVIEW", "CLOSED"] | None = None


class ImprovementActionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    issue_summary: str | None = Field(default=None, max_length=1000)
    root_cause: str | None = Field(default=None, max_length=1000)
    action_plan: str | None = Field(default=None, max_length=2000)
    owner_name: str = Field(min_length=1, max_length=120)
    target_text: str | None = Field(default=None, max_length=255)
    result_text: str | None = Field(default=None, max_length=1000)
    due_date: date | None = None
    status: Literal["OPEN", "IN_PROGRESS", "DONE", "CARRY_OVER"] = "OPEN"
    needs_jacky: bool = False


class ImprovementActionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    issue_summary: str | None = Field(default=None, max_length=1000)
    root_cause: str | None = Field(default=None, max_length=1000)
    action_plan: str | None = Field(default=None, max_length=2000)
    owner_name: str | None = Field(default=None, min_length=1, max_length=120)
    target_text: str | None = Field(default=None, max_length=255)
    result_text: str | None = Field(default=None, max_length=1000)
    due_date: date | None = None
    status: Literal["OPEN", "IN_PROGRESS", "DONE", "CARRY_OVER"] | None = None
    needs_jacky: bool | None = None


@router.get("/current")
def get_current_review(
    _: OpsAccess,
    session: SessionDependency,
) -> WeeklyReviewResponse:
    week_start, week_end = _current_week()
    review = session.scalar(select(WeeklyReview).where(WeeklyReview.week_end == week_end))
    return _review_response(session, review, week_start, week_end)


@router.patch("/current")
def update_current_review(
    update: WeeklyReviewUpdate,
    _: OpsAccess,
    session: SessionDependency,
) -> WeeklyReviewResponse:
    week_start, week_end = _current_week()
    review = _get_or_create_review(session, week_start, week_end)
    previous_status = review.status
    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(review, field_name, value)
    if review.status == "CLOSED" and previous_status != "CLOSED":
        _settle_week(session, week_start, week_end)
    session.commit()
    session.refresh(review)
    return _review_response(session, review, week_start, week_end)


class WeekListItem(BaseModel):
    week_start: date
    week_end: date
    status: str
    has_review: bool


class WeeklyEventItem(BaseModel):
    event_id: str
    intelligence_id: str
    event_type: str
    occurred_at: datetime
    title: str
    summary: str
    domain_code: str
    priority_level: str
    status: str
    owner_text: str | None
    deadline_at: datetime | None
    source_platforms: list[str] = Field(default_factory=list)


class WeeklyEventsPage(BaseModel):
    week_start: date
    week_end: date
    change_kind: str
    settled: bool
    items: list[WeeklyEventItem]
    next_cursor: str | None = None
    has_more: bool = False


@router.get("")
def list_reviews(
    _: OpsAccess,
    session: SessionDependency,
    weeks: int = 12,
) -> list[WeekListItem]:
    weeks = max(1, min(weeks, 52))
    _, current_end = _current_week()
    result: list[WeekListItem] = []
    for index in range(weeks):
        week_end = current_end - timedelta(days=7 * index)
        week_start = week_end - timedelta(days=6)
        review = session.scalar(select(WeeklyReview).where(WeeklyReview.week_end == week_end))
        result.append(
            WeekListItem(
                week_start=week_start,
                week_end=week_end,
                status=review.status if review else "DRAFT",
                has_review=review is not None,
            )
        )
    return result


@router.get("/{week_end}")
def get_review_by_week(
    week_end: date,
    _: OpsAccess,
    session: SessionDependency,
) -> WeeklyReviewResponse:
    _, current_end = _current_week()
    if week_end > current_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "FUTURE_WEEK_NOT_ALLOWED"},
        )
    week_start = week_end - timedelta(days=6)
    review = session.scalar(select(WeeklyReview).where(WeeklyReview.week_end == week_end))
    return _review_response(session, review, week_start, week_end)


@router.get("/{week_end}/events")
def get_review_events(
    week_end: date,
    change_kind: str,
    _: OpsAccess,
    session: SessionDependency,
    limit: int = 50,
    cursor: str | None = None,
) -> WeeklyEventsPage:
    limit = max(1, min(limit, 200))
    _, current_end = _current_week()
    if week_end > current_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "FUTURE_WEEK_NOT_ALLOWED"},
        )
    week_start = week_end - timedelta(days=6)
    review = session.scalar(select(WeeklyReview).where(WeeklyReview.week_end == week_end))
    snapshot = _latest_snapshot(session, week_end)
    settled = review is not None and review.status == "CLOSED" and snapshot is not None

    if settled:
        event_ids = (snapshot.change_event_ids_json or {}).get(change_kind, [])
        base = select(IntelligenceHistoryEvent).where(
            IntelligenceHistoryEvent.id.in_(event_ids or ["__none__"])
        )
    else:
        local_start, local_end = _week_window(week_start, week_end)
        base = select(IntelligenceHistoryEvent).where(
            IntelligenceHistoryEvent.event_type == change_kind,
            IntelligenceHistoryEvent.occurred_at >= local_start,
            IntelligenceHistoryEvent.occurred_at < local_end,
        )
    if cursor:
        cur_at, cur_id = _decode_event_cursor(cursor)
        base = base.where(
            (IntelligenceHistoryEvent.occurred_at > cur_at)
            | (
                (IntelligenceHistoryEvent.occurred_at == cur_at)
                & (IntelligenceHistoryEvent.id > cur_id)
            )
        )
    events = session.scalars(
        base.order_by(IntelligenceHistoryEvent.occurred_at, IntelligenceHistoryEvent.id).limit(
            limit + 1
        )
    ).all()
    has_more = len(events) > limit
    page = events[:limit]
    items = [_weekly_event_item(session, event) for event in page]
    next_cursor = (
        _encode_event_cursor(page[-1].occurred_at, page[-1].id) if has_more and page else None
    )
    return WeeklyEventsPage(
        week_start=week_start,
        week_end=week_end,
        change_kind=change_kind,
        settled=settled,
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def _encode_event_cursor(occurred_at: datetime, event_id: str) -> str:
    import base64

    aware = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=UTC)
    raw = f"{aware.isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_event_cursor(cursor: str) -> tuple[datetime, str]:
    import base64
    import binascii

    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        iso, event_id = raw.split("|", 1)
        return datetime.fromisoformat(iso), event_id
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"error_code": "INVALID_CURSOR"}
        ) from exc


def _weekly_event_item(session, event: IntelligenceHistoryEvent) -> WeeklyEventItem:  # type: ignore[no-untyped-def]
    from app.models import IntelligenceSource, Message

    snapshot = event.snapshot_json or {}
    card = session.get(IntelligenceObject, event.intelligence_id)
    platforms = sorted(
        set(
            session.scalars(
                select(Message.platform)
                .join(IntelligenceSource, IntelligenceSource.message_id == Message.id)
                .where(IntelligenceSource.intelligence_id == event.intelligence_id)
                .distinct()
            ).all()
        )
    )
    deadline_raw = snapshot.get("deadline_at")
    deadline_at = datetime.fromisoformat(deadline_raw) if isinstance(deadline_raw, str) else None
    return WeeklyEventItem(
        event_id=event.id,
        intelligence_id=event.intelligence_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        title=redact_sensitive_text(str(snapshot.get("title") or "")) or "（內容已遮蔽）",
        summary=redact_sensitive_text(str(snapshot.get("summary") or "")) or "（內容已遮蔽）",
        domain_code=str(snapshot.get("domain_code") or (card.domain_code if card else "")),
        priority_level=str(snapshot.get("priority_level") or (card.priority_level if card else "")),
        status=card.status if card else str(snapshot.get("status") or ""),
        owner_text=redact_sensitive_text(snapshot.get("owner_text")),
        deadline_at=deadline_at,
        source_platforms=platforms,
    )


@router.post("/current/actions", status_code=status.HTTP_201_CREATED)
def create_improvement_action(
    payload: ImprovementActionCreate,
    _: OpsAccess,
    session: SessionDependency,
) -> ImprovementActionResponse:
    week_start, week_end = _current_week()
    review = _get_or_create_review(session, week_start, week_end)
    action = ImprovementAction(review_id=review.id, **payload.model_dump())
    session.add(action)
    session.commit()
    session.refresh(action)
    return _action_response(action, week_end)


@router.patch("/actions/{action_id}")
def update_improvement_action(
    action_id: str,
    update: ImprovementActionUpdate,
    _: OpsAccess,
    session: SessionDependency,
) -> ImprovementActionResponse:
    action = session.get(ImprovementAction, action_id)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "IMPROVEMENT_ACTION_NOT_FOUND"},
        )
    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(action, field_name, value)
    review = session.get(WeeklyReview, action.review_id)
    session.commit()
    session.refresh(action)
    return _action_response(action, review.week_end if review else action.due_date or date.today())


def _current_week(reference: date | None = None) -> tuple[date, date]:
    today = reference or datetime.now(TAIPEI).date()
    week_start = today - timedelta(days=today.weekday())
    return week_start, week_start + timedelta(days=6)


def _get_or_create_review(session, week_start: date, week_end: date) -> WeeklyReview:  # type: ignore[no-untyped-def]
    review = session.scalar(select(WeeklyReview).where(WeeklyReview.week_end == week_end))
    if review is None:
        review = WeeklyReview(week_start=week_start, week_end=week_end)
        session.add(review)
        session.flush()
    return review


def _week_window(week_start: date, week_end: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(week_start, time.min, TAIPEI).astimezone(UTC)
    local_end = datetime.combine(week_end + timedelta(days=1), time.min, TAIPEI).astimezone(UTC)
    return local_start, local_end


def _change_counts_from_events(
    session, local_start: datetime, local_end: datetime  # type: ignore[no-untyped-def]
) -> tuple[dict[str, int], dict[str, list[str]], list[IntelligenceHistoryEvent]]:
    """Weekly change counts come from the append-only history, so a settled
    week's numbers never shift when a case is later updated."""
    events = session.scalars(
        select(IntelligenceHistoryEvent)
        .where(
            IntelligenceHistoryEvent.occurred_at >= local_start,
            IntelligenceHistoryEvent.occurred_at < local_end,
        )
        .order_by(IntelligenceHistoryEvent.occurred_at, IntelligenceHistoryEvent.id)
    ).all()
    counts: dict[str, int] = {}
    ids: dict[str, list[str]] = {}
    for event in events:
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
        ids.setdefault(event.event_type, []).append(event.id)
    return counts, ids, events


def _metric_signals(session) -> list[ReviewSignal]:  # type: ignore[no-untyped-def]
    snapshots = session.scalars(
        select(ExecutiveMetricSnapshot).where(
            ExecutiveMetricSnapshot.health_status.in_(("YELLOW", "RED"))
        )
    ).all()
    signals: list[ReviewSignal] = []
    for snapshot in snapshots:
        definition = DEFINITIONS_BY_CODE.get(snapshot.metric_code)
        if not definition:
            continue
        signals.append(
            ReviewSignal(
                code=snapshot.metric_code,
                label=definition["label"],
                health_status=snapshot.health_status,
                current_value=snapshot.current_value,
                target_value=snapshot.target_value,
                unit=definition["unit"],
                note=snapshot.note,
            )
        )
    signals.extend(ReviewSignal(**signal) for signal in revenue_review_signals(session))
    signals.extend(ReviewSignal(**signal) for signal in operational_review_signals(session))
    return signals


def _latest_snapshot(session, week_end: date):  # type: ignore[no-untyped-def]
    return session.scalar(
        select(WeeklyReviewSnapshot)
        .where(WeeklyReviewSnapshot.week_end == week_end)
        .order_by(WeeklyReviewSnapshot.version.desc())
    )


def _settle_week(session, week_start: date, week_end: date, actor: str = "OPS_USER") -> None:  # type: ignore[no-untyped-def]
    """Freeze the week's numbers when the review closes. Never overwrites an
    existing snapshot; a re-settle appends a new version for auditability."""
    live = _live_counts(session, week_start, week_end)
    previous = _latest_snapshot(session, week_end)
    version = (previous.version + 1) if previous is not None else 1
    session.add(
        WeeklyReviewSnapshot(
            week_end=week_end,
            version=version,
            change_counts_json=live["change_counts"],
            change_event_ids_json=live["change_event_ids"],
            total_intelligence=live["total"],
            urgent_intelligence=live["urgent"],
            decisions_needed=live["decisions"],
            metric_signals_json=[signal.model_dump() for signal in _metric_signals(session)],
            actor_text=actor,
        )
    )


def _live_counts(session, week_start: date, week_end: date) -> dict[str, object]:  # type: ignore[no-untyped-def]
    local_start, local_end = _week_window(week_start, week_end)
    change_counts, change_event_ids, events = _change_counts_from_events(
        session, local_start, local_end
    )

    # Use the final immutable event state within the week instead of the card's
    # mutable last_changed_at/current fields.  This keeps an unclosed historical
    # week stable even when the same case changes in a later week.
    latest_by_card: dict[str, IntelligenceHistoryEvent] = {}
    for event in events:
        latest_by_card[event.intelligence_id] = event
    cards = {
        card.id: card
        for card in session.scalars(
            select(IntelligenceObject).where(
                IntelligenceObject.id.in_(list(latest_by_card) or ["__none__"])
            )
        ).all()
    }
    urgent = 0
    decisions = 0
    for card_id, event in latest_by_card.items():
        snapshot = event.snapshot_json or {}
        card = cards.get(card_id)
        current_status = str(snapshot.get("status") or (card.status if card else ""))
        if current_status in CLOSED_INTELLIGENCE_STATUSES:
            continue
        priority = str(snapshot.get("priority_level") or (card.priority_level if card else ""))
        if priority in {"P0", "P1"}:
            urgent += 1
        requires_action = snapshot.get("requires_user_action")
        if requires_action is True or (
            requires_action is None and card is not None and card.requires_user_action
        ):
            decisions += 1
    return {
        "total": len(latest_by_card),
        "urgent": urgent,
        "decisions": decisions,
        "change_counts": change_counts,
        "change_event_ids": change_event_ids,
    }


def _review_response(session, review, week_start: date, week_end: date) -> WeeklyReviewResponse:  # type: ignore[no-untyped-def]
    snapshot = _latest_snapshot(session, week_end)
    if review is not None and review.status == "CLOSED" and snapshot is not None:
        total_intelligence = snapshot.total_intelligence
        urgent_intelligence = snapshot.urgent_intelligence
        decisions_needed = snapshot.decisions_needed
        change_counts = dict(snapshot.change_counts_json or {})
        metric_signals = [ReviewSignal(**signal) for signal in (snapshot.metric_signals_json or [])]
    else:
        live = _live_counts(session, week_start, week_end)
        total_intelligence = live["total"]
        urgent_intelligence = live["urgent"]
        decisions_needed = live["decisions"]
        change_counts = live["change_counts"]
        metric_signals = _metric_signals(session)

    action_rows = session.execute(
        select(ImprovementAction, WeeklyReview.week_end)
        .join(WeeklyReview, WeeklyReview.id == ImprovementAction.review_id)
        .where(
            or_(
                WeeklyReview.week_end == week_end,
                ImprovementAction.status.in_(OPEN_ACTION_STATUSES),
            )
        )
        .order_by(ImprovementAction.due_date.asc(), ImprovementAction.created_at.asc())
    ).all()
    actions = [_action_response(action, action_week_end) for action, action_week_end in action_rows]
    return WeeklyReviewResponse(
        id=review.id if review else None,
        week_start=week_start,
        week_end=week_end,
        status=review.status if review else "DRAFT",
        manager_name=review.manager_name if review else None,
        summary=review.summary if review else None,
        total_intelligence=total_intelligence,
        urgent_intelligence=urgent_intelligence,
        decisions_needed=decisions_needed,
        open_improvements=sum(action.status in OPEN_ACTION_STATUSES for action, _ in action_rows),
        change_counts=change_counts,
        metric_signals=metric_signals,
        actions=actions,
    )


def _action_response(action: ImprovementAction, review_week_end: date) -> ImprovementActionResponse:
    return ImprovementActionResponse(
        id=action.id,
        review_id=action.review_id,
        review_week_end=review_week_end,
        title=action.title,
        issue_summary=action.issue_summary,
        root_cause=action.root_cause,
        action_plan=action.action_plan,
        owner_name=action.owner_name,
        target_text=action.target_text,
        result_text=action.result_text,
        due_date=action.due_date,
        status=action.status,
        needs_jacky=action.needs_jacky,
        created_at=action.created_at,
        updated_at=action.updated_at,
    )
