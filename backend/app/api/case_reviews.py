from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.intelligence.case_matching import find_review_candidate
from app.models import (
    CaseMergeAudit,
    CaseReviewItem,
    IntelligenceObject,
    IntelligenceSource,
)

router = APIRouter(prefix="/api", tags=["case-review"])


class ReviewCard(BaseModel):
    id: str
    title: str
    summary: str
    priority_level: str
    domain_code: str
    event_type_code: str


class ReviewItemResponse(BaseModel):
    id: str
    score: float
    reasons: list[dict[str, object]]
    status: str
    intelligence: ReviewCard
    candidate: ReviewCard
    created_at: datetime


class ReviewResolution(BaseModel):
    action: Literal["MERGE", "KEEP_SEPARATE"]
    target_id: str | None = None
    actor_text: str = Field(default="OPS_USER", max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class MergeResponse(BaseModel):
    review_id: str
    resolution: str
    merge_audit_id: str | None = None


class ReviewScanResponse(BaseModel):
    examined: int
    created: int


class UnmergeResponse(BaseModel):
    audit_id: str
    reversed: bool


class MergeAuditResponse(BaseModel):
    id: str
    source_title: str
    target_title: str
    action: str
    actor_text: str
    created_at: datetime
    reversed_at: datetime | None


@router.get("/case-reviews")
def list_case_reviews(
    _: OpsAccess,
    session: SessionDependency,
    review_status: str = Query(default="PENDING", alias="status"),
) -> list[ReviewItemResponse]:
    reviews = session.scalars(
        select(CaseReviewItem)
        .where(CaseReviewItem.status == review_status)
        .order_by(CaseReviewItem.created_at.desc())
    ).all()
    result: list[ReviewItemResponse] = []
    for review in reviews:
        intelligence = session.get(IntelligenceObject, review.intelligence_id)
        candidate = session.get(IntelligenceObject, review.candidate_intelligence_id)
        if intelligence is None or candidate is None:
            continue
        result.append(
            ReviewItemResponse(
                id=review.id,
                score=review.score,
                reasons=review.reasons_json,
                status=review.status,
                intelligence=_review_card(intelligence),
                candidate=_review_card(candidate),
                created_at=review.created_at,
            )
        )
    return result


@router.post("/case-reviews/scan")
def scan_case_reviews(_: OpsAccess, session: SessionDependency) -> ReviewScanResponse:
    cutoff = datetime.now(UTC) - timedelta(days=14)
    cards = session.scalars(
        select(IntelligenceObject).where(
            IntelligenceObject.status != "ARCHIVED",
            IntelligenceObject.created_at >= cutoff,
        )
    ).all()
    existing_pairs = {
        tuple(sorted((item.intelligence_id, item.candidate_intelligence_id)))
        for item in session.scalars(select(CaseReviewItem)).all()
    }
    created = 0
    for card in cards:
        match = find_review_candidate(session, card)
        if match is None:
            continue
        pair = tuple(sorted((card.id, match.candidate_id)))
        if pair in existing_pairs:
            continue
        session.add(
            CaseReviewItem(
                intelligence_id=card.id,
                candidate_intelligence_id=match.candidate_id,
                score=match.score,
                reasons_json=match.reasons,
            )
        )
        existing_pairs.add(pair)
        created += 1
    session.commit()
    return ReviewScanResponse(examined=len(cards), created=created)


@router.post("/case-reviews/{review_id}/resolve")
def resolve_case_review(
    review_id: str,
    payload: ReviewResolution,
    _: OpsAccess,
    session: SessionDependency,
) -> MergeResponse:
    review = session.get(CaseReviewItem, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail={"error_code": "REVIEW_NOT_FOUND"})
    if review.status != "PENDING":
        raise HTTPException(status_code=409, detail={"error_code": "REVIEW_ALREADY_RESOLVED"})
    audit_id: str | None = None
    if payload.action == "MERGE":
        valid_targets = {review.intelligence_id, review.candidate_intelligence_id}
        target_id = payload.target_id or review.candidate_intelligence_id
        if target_id not in valid_targets:
            raise HTTPException(status_code=400, detail={"error_code": "INVALID_MERGE_TARGET"})
        source_id = (valid_targets - {target_id}).pop()
        audit_id = _merge_cards(
            session,
            source_id=source_id,
            target_id=target_id,
            actor=payload.actor_text,
            note=payload.note,
            score=review.score,
            reasons=review.reasons_json,
        )
    review.status = "RESOLVED"
    review.resolution = payload.action
    review.actor_text = payload.actor_text
    review.resolved_at = datetime.now(UTC)
    session.commit()
    return MergeResponse(review_id=review.id, resolution=payload.action, merge_audit_id=audit_id)


@router.post("/case-merges/{audit_id}/unmerge")
def unmerge_case(
    audit_id: str,
    _: OpsAccess,
    session: SessionDependency,
) -> UnmergeResponse:
    audit = session.get(CaseMergeAudit, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail={"error_code": "MERGE_AUDIT_NOT_FOUND"})
    if audit.reversed_at is not None:
        raise HTTPException(status_code=409, detail={"error_code": "MERGE_ALREADY_REVERSED"})
    source = session.get(IntelligenceObject, audit.source_intelligence_id)
    target = session.get(IntelligenceObject, audit.target_intelligence_id)
    if source is None or target is None:
        raise HTTPException(status_code=409, detail={"error_code": "MERGE_CANNOT_BE_REVERSED"})
    snapshot = audit.source_snapshot_json
    _restore(source, snapshot["source"])
    _restore(target, snapshot["target"])
    if audit.moved_message_ids_json:
        session.execute(
            delete(IntelligenceSource).where(
                IntelligenceSource.intelligence_id == target.id,
                IntelligenceSource.message_id.in_(audit.moved_message_ids_json),
            )
        )
    audit.reversed_at = datetime.now(UTC)
    session.commit()
    return UnmergeResponse(audit_id=audit.id, reversed=True)


@router.get("/case-merges")
def list_case_merges(
    _: OpsAccess,
    session: SessionDependency,
    active_only: bool = True,
) -> list[MergeAuditResponse]:
    query = select(CaseMergeAudit)
    if active_only:
        query = query.where(CaseMergeAudit.reversed_at.is_(None))
    audits = session.scalars(query.order_by(CaseMergeAudit.created_at.desc()).limit(20)).all()
    result: list[MergeAuditResponse] = []
    for audit in audits:
        source = session.get(IntelligenceObject, audit.source_intelligence_id)
        target = session.get(IntelligenceObject, audit.target_intelligence_id)
        result.append(
            MergeAuditResponse(
                id=audit.id,
                source_title=source.title if source is not None else "原案件",
                target_title=target.title if target is not None else "主案件",
                action=audit.action,
                actor_text=audit.actor_text,
                created_at=audit.created_at,
                reversed_at=audit.reversed_at,
            )
        )
    return result


def _merge_cards(
    session,
    *,
    source_id: str,
    target_id: str,
    actor: str,
    note: str | None,
    score: float,
    reasons: list[dict[str, object]],
) -> str:  # type: ignore[no-untyped-def]
    source = session.get(IntelligenceObject, source_id)
    target = session.get(IntelligenceObject, target_id)
    if source is None or target is None or source.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_CARDS"},
        )
    snapshots = {"source": _snapshot(source), "target": _snapshot(target)}
    existing = set(
        session.scalars(
            select(IntelligenceSource.message_id).where(
                IntelligenceSource.intelligence_id == target.id
            )
        ).all()
    )
    source_rows = session.scalars(
        select(IntelligenceSource)
        .where(IntelligenceSource.intelligence_id == source.id)
        .order_by(IntelligenceSource.evidence_order)
    ).all()
    next_order = len(existing) + 1
    moved: list[str] = []
    for row in source_rows:
        if row.message_id in existing:
            continue
        session.add(
            IntelligenceSource(
                intelligence_id=target.id,
                context_id=row.context_id,
                message_id=row.message_id,
                evidence_order=next_order,
            )
        )
        moved.append(row.message_id)
        next_order += 1
    target.facets_json = sorted(set(target.facets_json) | set(source.facets_json))
    if source.priority_score > target.priority_score:
        target.priority_score = source.priority_score
        target.priority_level = source.priority_level
        target.priority_reasons_json = source.priority_reasons_json
    target.requires_user_action = target.requires_user_action or source.requires_user_action
    target.requires_review = False
    source.status = "ARCHIVED"
    audit = CaseMergeAudit(
        source_intelligence_id=source.id,
        target_intelligence_id=target.id,
        source_context_id=source.context_id,
        action="MANUAL_MERGE",
        score=score,
        reasons_json=reasons,
        moved_message_ids_json=moved,
        source_snapshot_json=snapshots,
        actor_text=actor,
        note=note,
    )
    session.add(audit)
    session.flush()
    return audit.id


def _snapshot(card: IntelligenceObject) -> dict[str, object]:
    return {
        "status": card.status,
        "facets_json": card.facets_json,
        "priority_score": card.priority_score,
        "priority_level": card.priority_level,
        "priority_reasons_json": card.priority_reasons_json,
        "requires_user_action": card.requires_user_action,
        "requires_review": card.requires_review,
    }


def _restore(card: IntelligenceObject, snapshot: dict[str, object]) -> None:
    for key, value in snapshot.items():
        setattr(card, key, value)


def _review_card(card: IntelligenceObject) -> ReviewCard:
    return ReviewCard(
        id=card.id,
        title=card.title,
        summary=card.summary,
        priority_level=card.priority_level,
        domain_code=card.domain_code,
        event_type_code=card.event_type_code,
    )
