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


class IntelligenceSourceResponse(BaseModel):
    message_id: str
    evidence_order: int
    text: str | None
    source_created_at: datetime


class IntelligenceDetail(IntelligenceCard):
    sources: list[IntelligenceSourceResponse]


class IntelligenceUpdate(BaseModel):
    status: Literal[
        "OPEN",
        "IN_PROGRESS",
        "WAITING",
        "LIKELY_DONE",
        "DONE",
        "OVERDUE",
        "CANCELLED",
        "ARCHIVED",
    ] | None = None
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
    cards = session.scalars(
        query.order_by(
            IntelligenceObject.priority_level,
            IntelligenceObject.created_at.desc(),
        ).limit(limit)
    ).all()
    return [IntelligenceCard.model_validate(card) for card in cards]


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
        .order_by(IntelligenceSource.evidence_order)
    ).all()
    data = IntelligenceCard.model_validate(card).model_dump()
    return IntelligenceDetail(
        **data,
        sources=[
            IntelligenceSourceResponse(
                message_id=message.id,
                evidence_order=source.evidence_order,
                text=message.text,
                source_created_at=message.source_created_at,
            )
            for source, message in rows
        ],
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
    return IntelligenceCard.model_validate(card)


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
        sections[_section_for(card)].append(IntelligenceCard.model_validate(card))
    return DashboardToday(generated_at=now, total=len(cards), sections=sections)


def _section_for(card: IntelligenceObject) -> str:
    if card.type == "DECISION_REQUIRED":
        return "need_decision"
    if card.requires_user_action:
        return "need_action"
    if card.type == "RISK":
        return "risk"
    if card.type in {"FOLLOW_UP", "COMMITMENT"}:
        return "follow_up"
    if card.owner_text or card.type == "TASK":
        return "team_handling"
    return "fyi"


def _get_card_or_404(session, intelligence_id: str) -> IntelligenceObject:  # type: ignore[no-untyped-def]
    card = session.get(IntelligenceObject, intelligence_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "INTELLIGENCE_NOT_FOUND"},
        )
    return card
