from __future__ import annotations

from dataclasses import dataclass

from app.models import AttentionLevel


@dataclass(frozen=True)
class AttentionResult:
    level: str
    reasons: list[str]


def classify_attention(
    *,
    facets: list[str],
    priority_level: str,
    requires_user_action: bool,
) -> AttentionResult:
    """Route cards conservatively without guessing money or VIP thresholds.

    NOISE is intentionally never assigned automatically. Until the owner supplies
    amount thresholds and a VIP list, uncertain work stays visible to the team.
    """
    reasons: list[str] = []
    if requires_user_action:
        reasons.append("REQUIRES_OWNER_ACTION")
    if "DECISION_REQUIRED" in facets:
        reasons.append("DECISION_REQUIRED")
    if priority_level == "P0":
        reasons.append("P0_CRITICAL")
    if reasons:
        return AttentionResult(level=AttentionLevel.BOSS.value, reasons=reasons)
    return AttentionResult(level=AttentionLevel.TEAM.value, reasons=["TEAM_DEFAULT"])
