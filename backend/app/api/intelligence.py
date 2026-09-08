from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import IntelligenceObject, IntelligenceSource, Message

router = APIRouter(prefix="/api", tags=["intelligence"])


class IntelligenceCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    facets: list[str] = Field(default_factory=list)
    domain_code: str
    event_type_code: str
    title: str
    summary: str
    status: str
    owner_text: str | None
    deadline_at: datetime | None
    deadline_raw_text: str | None
    requires_user_action: bool
    confidence: float
    priority_score: int
    priority_level: str
    priority_reasons_json: list[dict[str, object]]
    requires_review: bool
    created_at: datetime
    source_platforms: list[str] = Field(default_factory=list)


class IntelligenceSourceResponse(BaseModel):
    message_id: str
    platform: str
    evidence_order: int
    text: str | None
    source_created_at: datetime


class CrossSourceSummary(BaseModel):
    """One case can gather LINE and Gmail evidence; this shows the mix at a glance."""

    is_cross_source: bool = False
    platforms: list[str] = Field(default_factory=list)
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    timeline_start: datetime | None = None
    timeline_end: datetime | None = None


class IntelligenceDetail(IntelligenceCard):
    sources: list[IntelligenceSourceResponse]
    cross_source: CrossSourceSummary = Field(default_factory=CrossSourceSummary)


class IntelligenceUpdate(BaseModel):
    status: (
        Literal[
            "OPEN",
            "IN_PROGRESS",
            "WAITING",
            "LIKELY_DONE",
            "DONE",
            "OVERDUE",
            "CANCELLED",
            "ARCHIVED",
        ]
        | None
    ) = None
    owner_text: str | None = Field(default=None, max_length=255)
    requires_user_action: bool | None = None


class DashboardToday(BaseModel):
    generated_at: datetime
    total: int
    sections: dict[str, list[IntelligenceCard]]


@router.get("/intelligence")
def list_intelligence(
    _: OpsAccess,
    session: SessionDependency,
    domain: str | None = None,
    priority: Literal["P0", "P1", "P2", "P3"] | None = None,
    card_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[IntelligenceCard]:
    query = select(IntelligenceObject)
    if domain:
        query = query.where(IntelligenceObject.domain_code == domain)
    if priority:
        query = query.where(IntelligenceObject.priority_level == priority)
    if card_status:
        query = query.where(IntelligenceObject.status == card_status)
    else:
        query = query.where(IntelligenceObject.status != "ARCHIVED")
    cards = session.scalars(
        query.order_by(
            IntelligenceObject.priority_level,
            IntelligenceObject.created_at.desc(),
        ).limit(limit)
    ).all()
    return [_card_response(session, card) for card in cards]


@router.get("/intelligence/{intelligence_id}")
def get_intelligence(
    intelligence_id: str,
    _: OpsAccess,
    session: SessionDependency,
) -> IntelligenceDetail:
    card = _get_card_or_404(session, intelligence_id)
    rows = session.execute(
        select(IntelligenceSource, Message)
        .join(Message, Message.id == IntelligenceSource.message_id)
        .where(IntelligenceSource.intelligence_id == intelligence_id)
        # Order by when each message actually happened so a merged LINE + Gmail
        # case reads as one true timeline; evidence_order only breaks ties.
        .order_by(Message.source_created_at, IntelligenceSource.evidence_order)
    ).all()
    data = _card_response(session, card).model_dump()
    sources = [
        IntelligenceSourceResponse(
            message_id=message.id,
            platform=message.platform,
            evidence_order=source.evidence_order,
            text=message.text,
            source_created_at=message.source_created_at,
        )
        for source, message in rows
    ]
    return IntelligenceDetail(
        **data,
        sources=sources,
        cross_source=_cross_source_summary(sources),
    )


@router.patch("/intelligence/{intelligence_id}")
def update_intelligence(
    intelligence_id: str,
    update: IntelligenceUpdate,
    _: OpsAccess,
    session: SessionDependency,
) -> IntelligenceCard:
    card = _get_card_or_404(session, intelligence_id)
    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(card, field_name, value)
    session.commit()
    session.refresh(card)
    return _card_response(session, card)


@router.get("/dashboard/today")
def dashboard_today(_: OpsAccess, session: SessionDependency) -> DashboardToday:
    now = datetime.now(UTC)
    local_now = now.astimezone(ZoneInfo("Asia/Taipei"))
    local_midnight = datetime.combine(local_now.date(), time.min, ZoneInfo("Asia/Taipei"))
    day_start = local_midnight.astimezone(UTC)
    cards = session.scalars(
        select(IntelligenceObject)
        .where(
            IntelligenceObject.created_at >= day_start,
            IntelligenceObject.status.not_in(["DONE", "ARCHIVED", "CANCELLED"]),
        )
        .order_by(IntelligenceObject.priority_level, IntelligenceObject.created_at.desc())
    ).all()
    sections: dict[str, list[IntelligenceCard]] = {
        "need_decision": [],
        "need_action": [],
        "follow_up": [],
        "risk": [],
        "team_handling": [],
        "fyi": [],
    }
    for card in cards:
        sections[_section_for(card)].append(_card_response(session, card))
    return DashboardToday(generated_at=now, total=len(cards), sections=sections)


def _section_for(card: IntelligenceObject) -> str:
    facets = set(card.facets_json or [card.type])
    if "DECISION_REQUIRED" in facets:
        return "need_decision"
    if card.requires_user_action:
        return "need_action"
    if card.owner_text or "TASK" in facets:
        return "team_handling"
    if "RISK" in facets:
        return "risk"
    if facets & {"FOLLOW_UP", "COMMITMENT"}:
        return "follow_up"
    return "fyi"


def _cross_source_summary(sources: list[IntelligenceSourceResponse]) -> CrossSourceSummary:
    if not sources:
        return CrossSourceSummary()
    breakdown: dict[str, int] = {}
    for item in sources:
        breakdown[item.platform] = breakdown.get(item.platform, 0) + 1
    times = [item.source_created_at for item in sources]
    return CrossSourceSummary(
        is_cross_source=len(breakdown) > 1,
        platforms=sorted(breakdown),
        source_breakdown=dict(sorted(breakdown.items())),
        timeline_start=min(times),
        timeline_end=max(times),
    )


def _get_card_or_404(session, intelligence_id: str) -> IntelligenceObject:  # type: ignore[no-untyped-def]
    card = session.get(IntelligenceObject, intelligence_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "INTELLIGENCE_NOT_FOUND"},
        )
    return card


def _card_response(session, card: IntelligenceObject) -> IntelligenceCard:  # type: ignore[no-untyped-def]
    platforms = session.scalars(
        select(Message.platform)
        .join(IntelligenceSource, IntelligenceSource.message_id == Message.id)
        .where(IntelligenceSource.intelligence_id == card.id)
        .distinct()
    ).all()
    data = IntelligenceCard.model_validate(card).model_dump()
    data["facets"] = card.facets_json or [card.type]
    data["source_platforms"] = sorted(platforms)
    return IntelligenceCard(**data)
