from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.intelligence.history import record_event
from app.models import (
    Attachment,
    AttentionLevel,
    IntelligenceFeedback,
    IntelligenceObject,
    IntelligenceSource,
    IntelligenceStatus,
    IntelligenceStatusAudit,
    Message,
)
from app.security.redaction import redact_sensitive_text

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
    attention_level: str
    attention_reasons_json: list[str]
    requires_review: bool
    created_at: datetime
    source_platforms: list[str] = Field(default_factory=list)
    lifecycle_stage: str
    blocker_type: str | None
    change_kind: str
    occurrence_count: int
    last_changed_at: datetime


class AttachmentEvidence(BaseModel):
    id: str
    filename: str | None
    media_type: str
    size_bytes: int | None
    processing_status: str


class IntelligenceSourceResponse(BaseModel):
    message_id: str
    platform: str
    evidence_order: int
    text: str | None
    source_created_at: datetime
    attachments: list[AttachmentEvidence] = Field(default_factory=list)


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
    attention_level: Literal["BOSS", "TEAM", "NOISE"] | None = None


class IntelligenceFeedbackRequest(BaseModel):
    attention_level: Literal["BOSS", "TEAM", "NOISE"] | None = None
    domain_code: str | None = Field(default=None, min_length=1, max_length=80)
    event_type_code: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["OPEN", "IN_PROGRESS", "WAITING", "DONE", "CANCELLED"] | None = None
    actor_text: str = Field(default="OPS_USER", max_length=120)
    reason: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    intelligence_id: str
    fields_changed: list[str]


class StatusActionRequest(BaseModel):
    action: Literal["CONFIRM_DONE", "REOPENED"]
    actor_text: str = Field(default="OPS_USER", min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class StatusAuditResponse(BaseModel):
    id: str
    from_status: str
    to_status: str
    action: str
    actor_text: str
    evidence_message_ids: list[str]
    note: str | None
    created_at: datetime


class DashboardToday(BaseModel):
    generated_at: datetime
    total: int
    sections: dict[str, list[IntelligenceCard]]


class TeamDailyDigest(BaseModel):
    date: date
    generated_at: datetime
    total: int
    by_priority: dict[str, int]
    by_domain: dict[str, int]
    cards: list[IntelligenceCard]


@router.get("/intelligence")
def list_intelligence(
    _: OpsAccess,
    session: SessionDependency,
    domain: str | None = None,
    priority: Literal["P0", "P1", "P2", "P3"] | None = None,
    attention_level: Literal["BOSS", "TEAM", "NOISE"] | None = None,
    card_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[IntelligenceCard]:
    query = select(IntelligenceObject)
    if domain:
        query = query.where(IntelligenceObject.domain_code == domain)
    if priority:
        query = query.where(IntelligenceObject.priority_level == priority)
    if attention_level:
        query = query.where(IntelligenceObject.attention_level == attention_level)
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
    sources = []
    for source, message in rows:
        attachments = session.scalars(
            select(Attachment)
            .where(Attachment.message_id == message.id)
            .order_by(Attachment.created_at)
        ).all()
        sources.append(
            IntelligenceSourceResponse(
                message_id=message.id,
                platform=message.platform,
                evidence_order=source.evidence_order,
                text=redact_sensitive_text(message.text),
                source_created_at=message.source_created_at,
                attachments=[
                    AttachmentEvidence(
                        id=item.id,
                        filename=redact_sensitive_text(item.filename),
                        media_type=item.media_type,
                        size_bytes=item.size_bytes,
                        processing_status=item.processing_status,
                    )
                    for item in attachments
                ],
            )
        )
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
    previous_status = card.status
    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(card, field_name, value)
    if card.status != previous_status:
        session.add(
            IntelligenceStatusAudit(
                intelligence_id=card.id,
                from_status=previous_status,
                to_status=card.status,
                action="MANUAL_STATUS_UPDATE",
                actor_text="OPS_USER",
                evidence_message_ids_json=[],
            )
        )
        record_event(
            session,
            card,
            _status_event_type(previous_status, card.status),
            actor_text="OPS_USER",
        )
    session.commit()
    session.refresh(card)
    return _card_response(session, card)


@router.post("/intelligence/{intelligence_id}/feedback")
def save_intelligence_feedback(
    intelligence_id: str,
    payload: IntelligenceFeedbackRequest,
    _: OpsAccess,
    session: SessionDependency,
) -> FeedbackResponse:
    card = _get_card_or_404(session, intelligence_id)
    changed: list[str] = []
    values = payload.model_dump(
        exclude={"actor_text", "reason"}, exclude_none=True
    )
    for field_name, corrected in values.items():
        previous = getattr(card, field_name)
        if previous == corrected:
            continue
        session.add(
            IntelligenceFeedback(
                intelligence_id=card.id,
                field_name=field_name,
                previous_value_json=previous,
                corrected_value_json=corrected,
                actor_text=payload.actor_text,
                reason=payload.reason,
            )
        )
        setattr(card, field_name, corrected)
        if field_name == "attention_level":
            card.attention_locked = True
        changed.append(field_name)
    if changed:
        card.change_kind = "MANUAL_CORRECTION"
        card.last_changed_at = datetime.now(UTC)
        record_event(session, card, "MANUAL_CORRECTION", actor_text=payload.actor_text)
    session.commit()
    return FeedbackResponse(intelligence_id=card.id, fields_changed=changed)


@router.post("/intelligence/{intelligence_id}/status-actions")
def apply_status_action(
    intelligence_id: str,
    payload: StatusActionRequest,
    _: OpsAccess,
    session: SessionDependency,
) -> IntelligenceCard:
    card = _get_card_or_404(session, intelligence_id)
    previous_status = card.status
    allowed_statuses = (
        {
            IntelligenceStatus.OPEN.value,
            IntelligenceStatus.IN_PROGRESS.value,
            IntelligenceStatus.WAITING.value,
            IntelligenceStatus.LIKELY_DONE.value,
            IntelligenceStatus.OVERDUE.value,
        }
        if payload.action == "CONFIRM_DONE"
        else {IntelligenceStatus.LIKELY_DONE.value, IntelligenceStatus.DONE.value}
    )
    if previous_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "INVALID_STATUS_TRANSITION", "current_status": previous_status},
        )
    target_status = (
        IntelligenceStatus.DONE.value
        if payload.action == "CONFIRM_DONE"
        else IntelligenceStatus.IN_PROGRESS.value
    )
    card.status = target_status
    card.change_kind = "UPDATED"
    card.last_changed_at = datetime.now(UTC)
    session.add(
        IntelligenceStatusAudit(
            intelligence_id=card.id,
            from_status=previous_status,
            to_status=target_status,
            action=payload.action,
            actor_text=payload.actor_text,
            evidence_message_ids_json=[],
            note=payload.note,
        )
    )
    record_event(
        session,
        card,
        "DONE" if payload.action == "CONFIRM_DONE" else "REOPENED",
        actor_text=payload.actor_text,
    )
    session.commit()
    session.refresh(card)
    return _card_response(session, card)


@router.get("/intelligence/{intelligence_id}/status-history")
def get_status_history(
    intelligence_id: str,
    _: OpsAccess,
    session: SessionDependency,
) -> list[StatusAuditResponse]:
    _get_card_or_404(session, intelligence_id)
    entries = session.scalars(
        select(IntelligenceStatusAudit)
        .where(IntelligenceStatusAudit.intelligence_id == intelligence_id)
        .order_by(IntelligenceStatusAudit.created_at, IntelligenceStatusAudit.id)
    ).all()
    return [
        StatusAuditResponse(
            id=entry.id,
            from_status=entry.from_status,
            to_status=entry.to_status,
            action=entry.action,
            actor_text=entry.actor_text,
            evidence_message_ids=entry.evidence_message_ids_json,
            note=entry.note,
            created_at=entry.created_at,
        )
        for entry in entries
    ]


@router.get("/dashboard/today")
def dashboard_today(_: OpsAccess, session: SessionDependency) -> DashboardToday:
    now = datetime.now(UTC)
    local_now = now.astimezone(ZoneInfo("Asia/Taipei"))
    local_midnight = datetime.combine(local_now.date(), time.min, ZoneInfo("Asia/Taipei"))
    day_start = local_midnight.astimezone(UTC)
    cards = session.scalars(
        select(IntelligenceObject)
        .where(
            IntelligenceObject.last_changed_at >= day_start,
            IntelligenceObject.status.not_in(["DONE", "ARCHIVED"]),
            IntelligenceObject.attention_level != AttentionLevel.NOISE.value,
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


@router.get("/digests/team/daily")
def team_daily_digest(
    _: OpsAccess,
    session: SessionDependency,
    digest_date: Annotated[date | None, Query(alias="date")] = None,
) -> TeamDailyDigest:
    now = datetime.now(UTC)
    timezone = ZoneInfo("Asia/Taipei")
    local_date = digest_date or now.astimezone(timezone).date()
    local_start = datetime.combine(local_date, time.min, timezone)
    start = local_start.astimezone(UTC)
    end = (local_start + timedelta(days=1)).astimezone(UTC)
    cards = session.scalars(
        select(IntelligenceObject)
        .where(
            IntelligenceObject.created_at >= start,
            IntelligenceObject.created_at < end,
            IntelligenceObject.attention_level == AttentionLevel.TEAM.value,
            IntelligenceObject.status.not_in(["ARCHIVED", "CANCELLED"]),
        )
        .order_by(IntelligenceObject.priority_level, IntelligenceObject.created_at.desc())
    ).all()
    by_priority: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    for card in cards:
        by_priority[card.priority_level] = by_priority.get(card.priority_level, 0) + 1
        by_domain[card.domain_code] = by_domain.get(card.domain_code, 0) + 1
    return TeamDailyDigest(
        date=local_date,
        generated_at=now,
        total=len(cards),
        by_priority=dict(sorted(by_priority.items())),
        by_domain=dict(sorted(by_domain.items())),
        cards=[_card_response(session, card) for card in cards],
    )


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


def _status_event_type(previous_status: str, new_status: str) -> str:
    if new_status == IntelligenceStatus.DONE.value:
        return "DONE"
    if new_status == IntelligenceStatus.CANCELLED.value:
        return "CANCELLED"
    if previous_status in {IntelligenceStatus.DONE.value, IntelligenceStatus.CANCELLED.value}:
        return "REOPENED"
    return "UPDATED"


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
    data["title"] = redact_sensitive_text(card.title) or "（內容已遮蔽）"
    data["summary"] = redact_sensitive_text(card.summary) or "（內容已遮蔽）"
    data["owner_text"] = redact_sensitive_text(card.owner_text)
    data["deadline_raw_text"] = redact_sensitive_text(card.deadline_raw_text)
    data["facets"] = card.facets_json or [card.type]
    data["source_platforms"] = sorted(platforms)
    return IntelligenceCard(**data)
