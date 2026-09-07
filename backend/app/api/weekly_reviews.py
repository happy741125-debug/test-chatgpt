from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.access import OpsAccess
from app.api.executive import DEFINITIONS_BY_CODE
from app.dependencies import SessionDependency
from app.models import (
    ExecutiveMetricSnapshot,
    ImprovementAction,
    IntelligenceObject,
    IntelligenceStatus,
    WeeklyReview,
)

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
    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(review, field_name, value)
    session.commit()
    session.refresh(review)
    return _review_response(session, review, week_start, week_end)


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


def _review_response(session, review, week_start: date, week_end: date) -> WeeklyReviewResponse:  # type: ignore[no-untyped-def]
    local_start = datetime.combine(week_start, time.min, TAIPEI).astimezone(UTC)
    local_end = datetime.combine(week_end + timedelta(days=1), time.min, TAIPEI).astimezone(UTC)
    week_filter = (
        IntelligenceObject.created_at >= local_start,
        IntelligenceObject.created_at < local_end,
    )
    total_intelligence = session.scalar(
        select(func.count(IntelligenceObject.id)).where(*week_filter)
    ) or 0
    urgent_intelligence = session.scalar(
        select(func.count(IntelligenceObject.id)).where(
            *week_filter,
            IntelligenceObject.priority_level.in_(("P0", "P1")),
            IntelligenceObject.status.not_in(CLOSED_INTELLIGENCE_STATUSES),
        )
    ) or 0
    decisions_needed = session.scalar(
        select(func.count(IntelligenceObject.id)).where(
            *week_filter,
            IntelligenceObject.requires_user_action.is_(True),
            IntelligenceObject.status.not_in(CLOSED_INTELLIGENCE_STATUSES),
        )
    ) or 0
    snapshots = session.scalars(
        select(ExecutiveMetricSnapshot).where(
            ExecutiveMetricSnapshot.health_status.in_(("YELLOW", "RED"))
        )
    ).all()
    metric_signals = []
    for snapshot in snapshots:
        definition = DEFINITIONS_BY_CODE.get(snapshot.metric_code)
        if not definition:
            continue
        metric_signals.append(
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
