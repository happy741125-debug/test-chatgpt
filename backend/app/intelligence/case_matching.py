from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IntelligenceObject

_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(frozen=True)
class CaseMatch:
    candidate_id: str
    score: float
    reasons: list[dict[str, object]]


def find_review_candidate(
    session: Session,
    incoming: IntelligenceObject,
    *,
    lookback_days: int = 14,
    minimum_score: float = 0.68,
) -> CaseMatch | None:
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    candidates = session.scalars(
        select(IntelligenceObject).where(
            IntelligenceObject.id != incoming.id,
            IntelligenceObject.status != "ARCHIVED",
            IntelligenceObject.created_at >= cutoff,
            IntelligenceObject.domain_code == incoming.domain_code,
        )
    ).all()
    matches = [_score(incoming, candidate) for candidate in candidates]
    qualified = [match for match in matches if match.score >= minimum_score]
    return max(qualified, key=lambda item: item.score, default=None)


def _score(incoming: IntelligenceObject, candidate: IntelligenceObject) -> CaseMatch:
    text_score = _dice(
        _normalise(f"{incoming.title} {incoming.summary}"),
        _normalise(f"{candidate.title} {candidate.summary}"),
    )
    event_match = incoming.event_type_code == candidate.event_type_code
    owner_match = bool(incoming.owner_text and incoming.owner_text == candidate.owner_text)
    score = min(
        1.0,
        text_score * 0.72 + (0.23 if event_match else 0) + (0.05 if owner_match else 0),
    )
    reasons: list[dict[str, object]] = [
        {"code": "TEXT_SIMILARITY", "value": round(text_score, 3)}
    ]
    if event_match:
        reasons.append({"code": "SAME_EVENT_TYPE", "value": True})
    if owner_match:
        reasons.append({"code": "SAME_OWNER", "value": True})
    return CaseMatch(candidate_id=candidate.id, score=round(score, 3), reasons=reasons)


def _normalise(value: str) -> str:
    return _SPACE.sub("", _PUNCTUATION.sub("", value.casefold()))


def _dice(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_pairs = {left[index : index + 2] for index in range(len(left) - 1)}
    right_pairs = {right[index : index + 2] for index in range(len(right) - 1)}
    if not left_pairs or not right_pairs:
        return 0.0
    return 2 * len(left_pairs & right_pairs) / (len(left_pairs) + len(right_pairs))
