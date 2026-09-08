from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.intelligence.signals import (
    classify_operational_signal,
    detect_lifecycle_stage,
    is_completion_for_event,
)
from app.models import (
    IntelligenceChangeAudit,
    IntelligenceObject,
    IntelligenceStatus,
    IntelligenceStatusAudit,
    Message,
)

_COMPLETION_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"已(?:經)?完成",
        r"完成了",
        r"已(?:經)?處理(?:好|完|完成)",
        r"處理好了",
        r"已(?:經)?(?:出貨|寄出|入庫|到貨|收到|匯款|付款|安排|解決)",
        r"(?:問題|異常)(?:已|已經)?解決",
        r"(?:可以|可)結案",
    )
)
_BLOCKING_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"尚未",
        r"還沒",
        r"未完成",
        r"沒有完成",
        r"尚待",
        r"是否(?:已|已經)",
        r"(?:完成|處理好|出貨|寄出|入庫|到貨|收到|匯款|付款|安排|解決)(?:了)?嗎",
        r"有沒有(?:完成|處理|出貨|寄出|入庫|到貨|收到|匯款|付款|安排|解決)",
    )
)


def has_completion_evidence(text: str | None, event_type: str | None = None) -> bool:
    normalized = "".join((text or "").split())
    if not normalized or any(pattern.search(normalized) for pattern in _BLOCKING_PATTERNS):
        return False
    generic_match = any(pattern.search(normalized) for pattern in _COMPLETION_PATTERNS)
    if event_type is None:
        return generic_match
    stage = detect_lifecycle_stage(text)
    return is_completion_for_event(event_type, stage)


def mark_likely_done_from_messages(
    session: Session,
    card: IntelligenceObject,
    message_ids: list[str],
) -> list[str]:
    """Mark a live card LIKELY_DONE when newly merged evidence says work finished."""
    if card.status in {IntelligenceStatus.ARCHIVED.value, IntelligenceStatus.CANCELLED.value}:
        return []
    initial_status = card.status
    messages = [session.get(Message, message_id) for message_id in message_ids]
    evidence_ids = []
    strongest_signal = None
    for message in messages:
        if message is None:
            continue
        signal = classify_operational_signal(
            message.text,
            event_type=card.event_type_code,
            previous_stage=card.lifecycle_stage,
            previous_status=card.status,
        )
        if signal.change_kind != "NO_CHANGE":
            strongest_signal = signal
        if signal.completion:
            evidence_ids.append(message.id)
    if strongest_signal is not None:
        previous_stage = card.lifecycle_stage
        if strongest_signal.stage != "UNKNOWN":
            card.lifecycle_stage = strongest_signal.stage
        card.blocker_type = strongest_signal.blocker_type
        card.change_kind = strongest_signal.change_kind
        card.last_changed_at = datetime.now(UTC)
        if strongest_signal.change_kind == "RECURRED":
            card.occurrence_count += 1
            card.status = IntelligenceStatus.IN_PROGRESS.value
        elif strongest_signal.change_kind == "CANCELLED":
            card.status = IntelligenceStatus.CANCELLED.value
        session.add(
            IntelligenceChangeAudit(
                intelligence_id=card.id,
                change_kind=strongest_signal.change_kind,
                previous_stage=previous_stage,
                current_stage=card.lifecycle_stage,
                blocker_type=card.blocker_type,
                evidence_message_ids_json=[message.id for message in messages if message],
            )
        )
    if not evidence_ids:
        return []
    if initial_status in {IntelligenceStatus.DONE.value, IntelligenceStatus.LIKELY_DONE.value}:
        return evidence_ids
    previous = card.status
    card.status = IntelligenceStatus.LIKELY_DONE.value
    session.add(
        IntelligenceStatusAudit(
            intelligence_id=card.id,
            from_status=previous,
            to_status=IntelligenceStatus.LIKELY_DONE.value,
            action="AUTO_LIKELY_DONE",
            actor_text="SYSTEM",
            evidence_message_ids_json=evidence_ids,
            note="後續訊息偵測到完成證據，等待人工確認。",
        )
    )
    return evidence_ids
