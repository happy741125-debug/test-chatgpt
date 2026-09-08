from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.order_ids import extract_order_ids
from app.ai.schemas import ContextAnalysisOutput, IntelligenceItem
from app.intelligence.attention import classify_attention
from app.intelligence.case_matching import find_review_candidate
from app.intelligence.completion import mark_likely_done_from_messages
from app.intelligence.history import record_event
from app.intelligence.priority import PriorityResult, calculate_priority
from app.models import (
    AIRun,
    AIRunStatus,
    CaseReviewItem,
    Context,
    IntelligenceChangeAudit,
    IntelligenceObject,
    IntelligenceSource,
)

_TYPE_ORDER = {
    "DECISION_REQUIRED": 0,
    "EVENT": 1,
    "TASK": 2,
    "RISK": 3,
    "COMMITMENT": 4,
    "FOLLOW_UP": 5,
    "DECISION": 6,
    "FYI": 7,
}


class IntelligenceMaterializer:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def materialize(self, context_id: str, output: ContextAnalysisOutput) -> list[str]:
        """Persist one main card per operational case, with AI facets kept as labels."""
        if not output.work_related or not output.items:
            return []
        with self.session_factory() as session:
            context = session.get(Context, context_id)
            if context is None:
                raise ValueError("Context does not exist")
            run = session.scalar(
                select(AIRun)
                .where(
                    AIRun.context_id == context_id,
                    AIRun.context_version == context.version,
                    AIRun.status == AIRunStatus.SUCCEEDED.value,
                )
                .order_by(AIRun.created_at.desc())
                .limit(1)
            )
            if run is None:
                raise ValueError("Successful AI run does not exist")

            representative = _representative(output.items)
            priority = _shared_priority(output.items)
            case_key = _case_key(context, output)
            facets = sorted(
                {item.type.value for item in output.items},
                key=lambda value: _TYPE_ORDER.get(value, 99),
            )
            owner = next((item.owner_text for item in output.items if item.owner_text), None)
            deadline_item = _deadline_item(output.items)
            evidence_ids = list(
                dict.fromkeys(
                    message_id for item in output.items for message_id in item.evidence_message_ids
                )
            )

            intelligence = session.scalar(
                select(IntelligenceObject).where(IntelligenceObject.case_key == case_key)
            )
            is_existing_case = intelligence is not None
            previous_summary = intelligence.summary if intelligence is not None else None
            previous_priority = intelligence.priority_score if intelligence is not None else 0
            previous_changed_at = intelligence.last_changed_at if intelligence is not None else None
            existing_sources = (
                set(
                    session.scalars(
                        select(IntelligenceSource.message_id).where(
                            IntelligenceSource.intelligence_id == intelligence.id
                        )
                    ).all()
                )
                if intelligence is not None
                else set()
            )
            if intelligence is None:
                fingerprint = _fingerprint(
                    representative.domain_code.value,
                    representative.event_type_code,
                    case_key,
                )
                intelligence = IntelligenceObject(
                    case_key=case_key,
                    facets_json=facets,
                    context_id=context_id,
                    context_version=context.version,
                    ai_run_id=run.id,
                    fingerprint=fingerprint,
                    type=representative.type.value,
                    domain_code=representative.domain_code.value,
                    event_type_code=representative.event_type_code,
                    title=representative.title,
                    summary=output.summary,
                    owner_text=owner,
                    deadline_at=(
                        deadline_item.deadline.resolved_at
                        if deadline_item is not None and deadline_item.deadline is not None
                        else None
                    ),
                    deadline_raw_text=(
                        deadline_item.deadline.raw_text
                        if deadline_item is not None and deadline_item.deadline is not None
                        else None
                    ),
                    requires_user_action=any(item.requires_user_action for item in output.items),
                    confidence=max(
                        output.overall_confidence, *(item.confidence for item in output.items)
                    ),
                    priority_score=priority.score,
                    priority_level=priority.level,
                    priority_reasons_json=priority.reasons,
                    requires_review=run.requires_review
                    or _needs_human_review(priority.level, _min_confidence(output)),
                )
                session.add(intelligence)
                session.flush()
                record_event(
                    session,
                    intelligence,
                    "NEW",
                    occurred_at=intelligence.created_at,
                    actor_text="SYSTEM",
                    evidence_message_ids=evidence_ids,
                )
            else:
                _update_case(
                    intelligence,
                    representative=representative,
                    output=output,
                    facets=facets,
                    owner=owner,
                    deadline_item=deadline_item,
                    priority=priority,
                    requires_review=run.requires_review,
                )

            if not intelligence.attention_locked:
                attention = classify_attention(
                    facets=intelligence.facets_json or [intelligence.type],
                    priority_level=intelligence.priority_level,
                    requires_user_action=intelligence.requires_user_action,
                )
                intelligence.attention_level = attention.level
                intelligence.attention_reasons_json = attention.reasons

            next_order = len(existing_sources) + 1
            added_message_ids: list[str] = []
            for message_id in evidence_ids:
                if message_id in existing_sources:
                    continue
                session.add(
                    IntelligenceSource(
                        intelligence_id=intelligence.id,
                        context_id=context_id,
                        message_id=message_id,
                        evidence_order=next_order,
                    )
                )
                added_message_ids.append(message_id)
                next_order += 1
            mark_likely_done_from_messages(session, intelligence, added_message_ids)
            if (
                is_existing_case
                and intelligence.last_changed_at == previous_changed_at
                and previous_summary != output.summary
            ):
                intelligence.change_kind = (
                    "DETERIORATED"
                    if intelligence.priority_score > previous_priority
                    else "UPDATED"
                )
                intelligence.last_changed_at = datetime.now(UTC)
                session.add(
                    IntelligenceChangeAudit(
                        intelligence_id=intelligence.id,
                        change_kind=intelligence.change_kind,
                        previous_stage=intelligence.lifecycle_stage,
                        current_stage=intelligence.lifecycle_stage,
                        blocker_type=intelligence.blocker_type,
                        evidence_message_ids_json=added_message_ids,
                    )
                )
                record_event(
                    session,
                    intelligence,
                    intelligence.change_kind,
                    occurred_at=intelligence.last_changed_at,
                    actor_text="SYSTEM",
                    evidence_message_ids=added_message_ids,
                )
            if not is_existing_case and not extract_order_ids(
                " ".join(
                    [output.summary]
                    + [f"{item.title} {item.summary}" for item in output.items]
                )
            ):
                match = find_review_candidate(session, intelligence)
                if match is not None:
                    session.add(
                        CaseReviewItem(
                            intelligence_id=intelligence.id,
                            candidate_intelligence_id=match.candidate_id,
                            score=match.score,
                            reasons_json=match.reasons,
                        )
                    )
                    intelligence.requires_review = True
            session.commit()
            return [intelligence.id]


class IntelligencePipeline:
    def __init__(self, gateway, materializer: IntelligenceMaterializer) -> None:  # type: ignore[no-untyped-def]
        self.gateway = gateway
        self.materializer = materializer

    def __call__(self, context_id: str) -> list[str]:
        output = self.gateway.analyze_context(context_id)
        return self.materializer.materialize(context_id, output)


# High-priority cards demand a stricter confidence bar before they may skip a human.
_HIGH_PRIORITY_REVIEW_CONFIDENCE = 0.9


def _min_confidence(output: ContextAnalysisOutput) -> float:
    return min((item.confidence for item in output.items), default=output.overall_confidence)


def _needs_human_review(priority_level: str, confidence: float) -> bool:
    """P0/P1 items must be reviewed by a human unless the model is highly confident."""
    if priority_level in {"P0", "P1"}:
        return confidence < _HIGH_PRIORITY_REVIEW_CONFIDENCE
    return False


def _representative(items: list[IntelligenceItem]) -> IntelligenceItem:
    return min(items, key=lambda item: _TYPE_ORDER.get(item.type.value, 99))


def _deadline_item(items: list[IntelligenceItem]) -> IntelligenceItem | None:
    with_deadline = [item for item in items if item.deadline is not None]
    if not with_deadline:
        return None
    resolved = [item for item in with_deadline if item.deadline and item.deadline.resolved_at]
    if resolved:
        return min(resolved, key=lambda item: item.deadline.resolved_at)  # type: ignore[union-attr]
    return with_deadline[0]


def _shared_priority(items: list[IntelligenceItem]) -> PriorityResult:
    results = [calculate_priority(item) for item in items]
    strongest = max(results, key=lambda result: result.score)
    reasons: list[dict[str, int | str]] = []
    seen: set[str] = set()
    for result in sorted(results, key=lambda value: value.score, reverse=True):
        for reason in result.reasons:
            code = str(reason["code"])
            if code not in seen:
                reasons.append(reason)
                seen.add(code)
    return PriorityResult(score=strongest.score, level=strongest.level, reasons=reasons)


def _case_key(context: Context, output: ContextAnalysisOutput) -> str:
    text = " ".join([output.summary] + [f"{item.title} {item.summary}" for item in output.items])
    order_ids = sorted(set(extract_order_ids(text)))
    if order_ids:
        identity = "orders:" + ",".join(order_ids)
    else:
        identity = f"context:{context.id}:{context.version}"
    return sha256(identity.encode("utf-8")).hexdigest()


def _update_case(
    intelligence: IntelligenceObject,
    *,
    representative: IntelligenceItem,
    output: ContextAnalysisOutput,
    facets: list[str],
    owner: str | None,
    deadline_item: IntelligenceItem | None,
    priority: PriorityResult,
    requires_review: bool,
) -> None:
    current_rank = _TYPE_ORDER.get(intelligence.type, 99)
    incoming_rank = _TYPE_ORDER.get(representative.type.value, 99)
    if incoming_rank <= current_rank:
        intelligence.type = representative.type.value
        intelligence.domain_code = representative.domain_code.value
        intelligence.event_type_code = representative.event_type_code
        intelligence.title = representative.title
    intelligence.summary = output.summary
    intelligence.facets_json = sorted(
        set(intelligence.facets_json or []) | set(facets),
        key=lambda value: _TYPE_ORDER.get(value, 99),
    )
    intelligence.owner_text = owner or intelligence.owner_text
    if deadline_item is not None and deadline_item.deadline is not None:
        incoming_deadline = deadline_item.deadline.resolved_at
        if intelligence.deadline_at is None or (
            incoming_deadline is not None
            and _as_utc(incoming_deadline) < _as_utc(intelligence.deadline_at)
        ):
            intelligence.deadline_at = incoming_deadline
            intelligence.deadline_raw_text = deadline_item.deadline.raw_text
    intelligence.requires_user_action = intelligence.requires_user_action or any(
        item.requires_user_action for item in output.items
    )
    intelligence.confidence = max(
        intelligence.confidence,
        output.overall_confidence,
        *(item.confidence for item in output.items),
    )
    if priority.score >= intelligence.priority_score:
        intelligence.priority_score = priority.score
        intelligence.priority_level = priority.level
        intelligence.priority_reasons_json = priority.reasons
    intelligence.requires_review = (
        intelligence.requires_review
        or requires_review
        or _needs_human_review(priority.level, _min_confidence(output))
    )
def _fingerprint(domain: str, event_type: str, case_key: str) -> str:
    canonical = "|".join((domain, event_type, case_key))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
