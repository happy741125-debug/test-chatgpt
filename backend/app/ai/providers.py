from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol


@dataclass(frozen=True)
class AnalysisMessage:
    id: str
    sequence: int
    sender_identity_id: str | None
    message_type: str
    text: str | None
    source_created_at: str


@dataclass(frozen=True)
class AnalysisRequest:
    context_id: str
    context_version: int
    timezone: str
    reference_time: str
    prompt_name: str
    prompt_version: int
    prompt_template: str
    messages: tuple[AnalysisMessage, ...]


@dataclass(frozen=True)
class ProviderResponse:
    output: dict[str, Any]
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_microunits: int | None = None


class AIProvider(Protocol):
    name: str
    model: str

    def analyze(self, request: AnalysisRequest) -> ProviderResponse: ...


MockOutput = dict[str, Any] | Callable[[AnalysisRequest], dict[str, Any]]


class MockAIProvider:
    """Deterministic provider for CI; it never makes a network request."""

    name = "mock"
    model = "mock-intelligence-v1"

    def __init__(self, output: MockOutput) -> None:
        self.output = output
        self.requests: list[AnalysisRequest] = []

    def analyze(self, request: AnalysisRequest) -> ProviderResponse:
        self.requests.append(request)
        output = self.output(request) if callable(self.output) else self.output
        return ProviderResponse(
            output=output,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_microunits=0,
        )


class RuleBasedAIProvider:
    """Free deterministic development provider for end-to-end pipeline tests."""

    name = "rule-based"
    model = "huoda-rules-v1"

    _event_rules = (
        ("WAREHOUSE_OPERATIONS", "STOCK_SHORTAGE", ("缺貨", "短缺", "不足", "缺口")),
        ("WAREHOUSE_OPERATIONS", "OUTBOUND_DELAY", ("出貨延誤", "出貨延遲", "晚出貨")),
        ("CUSTOMER", "CUSTOMER_COMPLAINT", ("客訴", "抱怨", "投訴")),
        ("FINANCE_COST", "COST_ANOMALY", ("成本異常", "異常支出", "費用異常")),
        ("PEOPLE", "STAFFING_GAP", ("缺工", "人力不足", "臨時請假")),
        ("ALLIANCE_WAREHOUSE", "ALLIANCE_ISSUE", ("聯盟倉異常", "合作倉異常", "SOP 落差")),
        ("SYSTEM", "SYSTEM_INCIDENT", ("系統異常", "WMS 異常", "API 異常", "服務中斷")),
        ("SALES", "COMMERCIAL_PROGRESS", ("新客戶", "報價", "提案", "合約")),
        ("MANAGEMENT", "MANAGEMENT_DECISION", ("需要決定", "請決定", "等主管決定")),
    )

    def analyze(self, request: AnalysisRequest) -> ProviderResponse:
        text_messages = [message for message in request.messages if message.text]
        combined = "\n".join(message.text or "" for message in text_messages)
        matches = [
            (domain, event_type, keywords)
            for domain, event_type, keywords in self._event_rules
            if any(keyword.lower() in combined.lower() for keyword in keywords)
        ]
        if not matches:
            return ProviderResponse(
                output={
                    "work_related": False,
                    "noise_type": "GENERAL_CHAT",
                    "summary": "未偵測到明確的貨達營運事件。",
                    "entities": [],
                    "items": [],
                    "overall_confidence": 0.8,
                },
                input_tokens=_estimate_tokens(combined),
                output_tokens=30,
                estimated_cost_microunits=0,
            )

        items: list[dict[str, Any]] = []
        for domain, event_type, keywords in matches:
            evidence_ids = [
                message.id
                for message in text_messages
                if any(keyword.lower() in (message.text or "").lower() for keyword in keywords)
            ]
            title = _event_title(event_type, combined)
            items.append(
                _item(
                    item_type="EVENT",
                    domain=domain,
                    event_type=event_type,
                    title=title,
                    summary=_compact(combined),
                    evidence_ids=evidence_ids,
                    owner=_owner(combined),
                    deadline=_deadline(request.reference_time, combined),
                    requires_user_action=any(
                        keyword in combined for keyword in ("需要決定", "請決定", "請老闆")
                    ),
                    confidence=0.88,
                )
            )

        primary_ids = [message.id for message in text_messages]
        owner = _owner(combined)
        deadline = _deadline(request.reference_time, combined)
        if any(keyword in combined for keyword in ("補貨", "叫貨", "處理", "確認")):
            task_event_type = (
                "REPLENISHMENT"
                if "補貨" in combined or "叫貨" in combined
                else matches[0][1]
            )
            items.append(
                _item(
                    item_type="TASK",
                    domain=matches[0][0],
                    event_type=task_event_type,
                    title="處理營運事件",
                    summary=_compact(combined),
                    evidence_ids=primary_ids,
                    owner=owner,
                    deadline=deadline,
                    requires_user_action=False,
                    confidence=0.82,
                )
            )
        if deadline is not None:
            items.append(
                _item(
                    item_type="COMMITMENT",
                    domain=matches[0][0],
                    event_type=matches[0][1],
                    title="已有預計完成時間",
                    summary=_compact(combined),
                    evidence_ids=primary_ids,
                    owner=owner,
                    deadline=deadline,
                    requires_user_action=False,
                    confidence=0.8,
                )
            )
        risk_event_types = {
            "STOCK_SHORTAGE",
            "OUTBOUND_DELAY",
            "CUSTOMER_COMPLAINT",
            "SYSTEM_INCIDENT",
            "COST_ANOMALY",
        }
        if any(event_type in risk_event_types for _, event_type, _ in matches):
            items.append(
                _item(
                    item_type="RISK",
                    domain=matches[0][0],
                    event_type=matches[0][1],
                    title="可能影響營運，需持續追蹤",
                    summary=_compact(combined),
                    evidence_ids=primary_ids,
                    owner=owner,
                    deadline=deadline,
                    requires_user_action=False,
                    confidence=0.78,
                )
            )

        evidence_id = text_messages[0].id
        entities: list[dict[str, Any]] = []
        customer = re.search(r"([A-Za-z0-9\u4e00-\u9fff_-]{1,16}客戶)", combined)
        if customer:
            entities.append(
                {
                    "type": "CUSTOMER",
                    "text": customer.group(1),
                    "evidence_message_id": evidence_id,
                    "confidence": 0.85,
                }
            )
        if owner:
            entities.append(
                {
                    "type": "PERSON",
                    "text": owner,
                    "evidence_message_id": evidence_id,
                    "confidence": 0.75,
                }
            )
        output = {
            "work_related": True,
            "noise_type": None,
            "summary": _compact(combined),
            "entities": entities,
            "items": items,
            "overall_confidence": 0.82,
        }
        return ProviderResponse(
            output=output,
            input_tokens=_estimate_tokens(combined),
            output_tokens=_estimate_tokens(str(output)),
            estimated_cost_microunits=0,
        )


def _item(
    *,
    item_type: str,
    domain: str,
    event_type: str,
    title: str,
    summary: str,
    evidence_ids: list[str],
    owner: str | None,
    deadline: dict[str, Any] | None,
    requires_user_action: bool,
    confidence: float,
) -> dict[str, Any]:
    return {
        "type": item_type,
        "domain_code": domain,
        "event_type_code": event_type,
        "title": title,
        "summary": summary,
        "owner_text": owner,
        "deadline": deadline,
        "requires_user_action": requires_user_action,
        "evidence_message_ids": evidence_ids,
        "confidence": confidence,
    }


def _event_title(event_type: str, text: str) -> str:
    labels = {
        "STOCK_SHORTAGE": "發現庫存短缺",
        "OUTBOUND_DELAY": "出貨可能延誤",
        "CUSTOMER_COMPLAINT": "收到客戶反映",
        "COST_ANOMALY": "發現成本異常",
        "STAFFING_GAP": "人力可能不足",
        "ALLIANCE_ISSUE": "聯盟倉出現異常",
        "SYSTEM_INCIDENT": "系統發生異常",
        "COMMERCIAL_PROGRESS": "商務進度更新",
        "MANAGEMENT_DECISION": "有事項需要決定",
    }
    quantity = re.search(r"\d+\s*(?:箱|件|筆|單)", text)
    suffix = f" {quantity.group(0)}" if quantity else ""
    return f"{labels[event_type]}{suffix}"


def _owner(text: str) -> str | None:
    match = re.search(r"(?:請|由|交給)?\s*([A-Z][A-Za-z]{1,30})\s*(?:已|去|跟|負責|處理)", text)
    return match.group(1) if match else None


def _deadline(reference_time: str, text: str) -> dict[str, Any] | None:
    raw_text: str | None = None
    hour = 17
    if "明天下午" in text:
        raw_text, hour = "明天下午", 15
    elif "明天" in text:
        raw_text = "明天"
    elif "今天" in text:
        raw_text = "今天"
    if raw_text is None:
        return None
    reference = datetime.fromisoformat(reference_time)
    target = reference + timedelta(days=1 if raw_text.startswith("明天") else 0)
    target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
    return {
        "raw_text": raw_text,
        "resolved_at": target.isoformat(),
        "timezone": "Asia/Taipei",
        "confidence": 0.75,
    }


def _compact(text: str) -> str:
    return " ".join(text.split())[:1000]


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
