from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import IntelligenceObject, IntelligenceStatus, IntelligenceStatusAudit, Message

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


def has_completion_evidence(text: str | None) -> bool:
    normalized = "".join((text or "").split())
    if not normalized or any(pattern.search(normalized) for pattern in _BLOCKING_PATTERNS):
        return False
    return any(pattern.search(normalized) for pattern in _COMPLETION_PATTERNS)


def mark_likely_done_from_messages(
    session: Session,
    card: IntelligenceObject,
    message_ids: list[str],
) -> list[str]:
    """Mark a live card LIKELY_DONE when newly merged evidence says work finished."""
    if card.status not in {
        IntelligenceStatus.OPEN.value,
        IntelligenceStatus.IN_PROGRESS.value,
        IntelligenceStatus.WAITING.value,
        IntelligenceStatus.OVERDUE.value,
    }:
        return []
    messages = [session.get(Message, message_id) for message_id in message_ids]
    evidence_ids = [
        message.id
        for message in messages
        if message is not None and has_completion_evidence(message.text)
    ]
    if not evidence_ids:
        return []
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
