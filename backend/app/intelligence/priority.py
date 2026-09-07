from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.ai.schemas import IntelligenceItem


@dataclass(frozen=True)
class PriorityResult:
    score: int
    level: str
    reasons: list[dict[str, int | str]]


def calculate_priority(item: IntelligenceItem, *, now: datetime | None = None) -> PriorityResult:
    current = now or datetime.now(UTC)
    reasons: list[dict[str, int | str]] = []

    if item.requires_user_action:
        reasons.append({"code": "USER_ACTION", "score": 30})
    if item.type.value == "DECISION_REQUIRED":
        reasons.append({"code": "DECISION_REQUIRED", "score": 30})

    deadline_score = _deadline_urgency(item, current)
    if deadline_score:
        reasons.append({"code": "DEADLINE_URGENCY", "score": deadline_score})

    high_impact_domains = {"WAREHOUSE_OPERATIONS", "CUSTOMER", "SYSTEM"}
    impact_score = 20 if item.domain_code.value in high_impact_domains else 10
    reasons.append({"code": "BUSINESS_IMPACT", "score": impact_score})

    if item.type.value == "RISK":
        reasons.append({"code": "RISK", "score": 15})
    if item.deadline is not None:
        reasons.append({"code": "HAS_DEADLINE", "score": 5})

    urgent_signal = any(
        keyword in f"{item.title} {item.summary}"
        for keyword in ("急單", "插單", "趕單", "務必", "盡快", "優先", "緊急")
    )
    if urgent_signal:
        reasons.append({"code": "URGENT_SIGNAL", "score": 20})

    hard_rule = any(
        keyword in f"{item.title} {item.summary}"
        for keyword in ("全面故障", "法律事件", "重大出貨事故", "大額財務異常")
    )
    score = min(100, sum(int(reason["score"]) for reason in reasons))
    if hard_rule:
        score = max(score, 80)
        reasons.append({"code": "CRITICAL_HARD_RULE", "score": 80})

    level = "P0" if score >= 80 else "P1" if score >= 60 else "P2" if score >= 30 else "P3"
    return PriorityResult(score=score, level=level, reasons=reasons)


def _deadline_urgency(item: IntelligenceItem, now: datetime) -> int:
    if item.deadline is None:
        return 0
    if item.deadline.resolved_at is None:
        return 10 if any(word in item.deadline.raw_text for word in ("今天", "明天")) else 0
    deadline = item.deadline.resolved_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    delta = deadline.astimezone(UTC) - now.astimezone(UTC)
    if delta <= timedelta(0):
        return 20
    if delta <= timedelta(hours=24):
        return 20
    if delta <= timedelta(days=3):
        return 15
    if delta <= timedelta(days=7):
        return 10
    return 0
