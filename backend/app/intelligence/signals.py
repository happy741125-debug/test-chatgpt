from __future__ import annotations

import re
from dataclasses import dataclass

_QUESTION = re.compile(r"(?:是否|有沒有|請問|嗎[？?]?$)")
_NEGATION = re.compile(r"(?:尚未|還沒|未完成|沒有完成|尚待|無法|不能|卡住)")

_STAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PAYMENT_RECONCILED", re.compile(r"(?:已|完成)?(?:核帳|對帳完成|確認入帳|款項已收到)")),
    ("PAYMENT_REPORTED", re.compile(r"(?:已匯款|已付款|款項已轉|匯款完成)")),
    (
        "SYSTEM_RECOVERED",
        re.compile(r"(?:系統|WMS|API|問題|異常).*(?:已恢復|已修復|修復完成|已解決)"),
    ),
    ("DELIVERED", re.compile(r"(?:客戶|收件人)?.*(?:已簽收|已送達|已收到貨)")),
    ("OUTBOUND_SHIPPED", re.compile(r"(?:已出貨|已寄出|出貨完成|交寄完成|已派件)")),
    ("INBOUND_RECEIVED", re.compile(r"(?:已入庫|入庫完成|點收完成|驗收完成)")),
    ("CANCELLED", re.compile(r"(?:已取消|取消訂單|不用處理|作廢)")),
    ("GENERAL_COMPLETED", re.compile(r"(?:已處理完成|已經處理好|處理完成|全部完成)")),
)

_BLOCKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("STOCK", ("缺貨", "庫存不足", "沒貨", "調不到")),
    ("DOCUMENT", ("缺文件", "缺資料", "待補件", "尚未提供")),
    ("CUSTOMER_WAITING", ("等客戶", "待客戶", "客戶尚未", "等回覆")),
    ("SYSTEM", ("系統異常", "WMS異常", "API異常", "上傳不了")),
    ("CAPACITY", ("人力不足", "缺工", "塞車", "爆量", "來不及")),
    ("PAYMENT", ("尚未匯款", "未付款", "款項未到", "未入帳")),
)

_COMPLETION_STAGES = {
    "INBOUND_OPERATION": {"INBOUND_RECEIVED", "GENERAL_COMPLETED"},
    "OUTBOUND_OPERATION": {"OUTBOUND_SHIPPED", "DELIVERED", "GENERAL_COMPLETED"},
    "OUTBOUND_DELAY": {"OUTBOUND_SHIPPED", "DELIVERED", "GENERAL_COMPLETED"},
    "URGENT_ORDER": {"OUTBOUND_SHIPPED", "DELIVERED", "GENERAL_COMPLETED"},
    "DISPATCH_REQUEST": {"OUTBOUND_SHIPPED", "DELIVERED"},
    "PAYMENT_STATUS": {"PAYMENT_RECONCILED"},
    "SYSTEM_INCIDENT": {"SYSTEM_RECOVERED"},
    "SHIPMENT_DISCREPANCY": {"DELIVERED", "GENERAL_COMPLETED"},
}


@dataclass(frozen=True)
class OperationalSignal:
    stage: str
    blocker_type: str | None
    change_kind: str
    completion: bool


def detect_lifecycle_stage(text: str | None) -> str:
    normalized = "".join((text or "").split())
    if not normalized or _QUESTION.search(normalized) or _NEGATION.search(normalized):
        return "UNKNOWN"
    for stage, pattern in _STAGE_PATTERNS:
        if pattern.search(normalized):
            return stage
    return "UNKNOWN"


def detect_blocker(text: str | None) -> str | None:
    normalized = "".join((text or "").split())
    for blocker, keywords in _BLOCKERS:
        if any(keyword in normalized for keyword in keywords):
            return blocker
    return None


def is_completion_for_event(event_type: str, stage: str) -> bool:
    return stage in _COMPLETION_STAGES.get(event_type, set())


def classify_operational_signal(
    text: str | None,
    *,
    event_type: str,
    previous_stage: str = "UNKNOWN",
    previous_status: str = "OPEN",
) -> OperationalSignal:
    normalized = "".join((text or "").split())
    stage = detect_lifecycle_stage(text)
    blocker = detect_blocker(text)
    completion = is_completion_for_event(event_type, stage)
    if previous_status in {"DONE", "LIKELY_DONE"} and blocker:
        change = "RECURRED"
    elif any(word in normalized for word in ("改期", "延期", "延後", "改到")):
        change = "RESCHEDULED"
    elif stage == "CANCELLED":
        change = "CANCELLED"
    elif blocker:
        change = "DETERIORATED"
    elif completion:
        change = "LIKELY_DONE"
    elif stage != "UNKNOWN" and stage != previous_stage:
        change = "UPDATED"
    else:
        change = "NO_CHANGE"
    return OperationalSignal(
        stage=stage,
        blocker_type=blocker,
        change_kind=change,
        completion=completion,
    )
