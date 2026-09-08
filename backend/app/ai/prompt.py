from __future__ import annotations

from app.ai.providers import AnalysisRequest
from app.ai.schemas import DomainCode, IntelligenceType, NoiseType


def build_extraction_prompt(request: AnalysisRequest) -> str:
    """Structured-output instructions shared by every LLM shadow provider."""
    domains = ", ".join(code.value for code in DomainCode)
    types = ", ".join(code.value for code in IntelligenceType)
    noises = ", ".join(code.value for code in NoiseType)
    lines = [
        "你是貨達倉儲營運的情報分析器。閱讀以下一段對話，只輸出一個 JSON 物件，不要多餘文字。",
        "",
        "JSON 結構（欄位固定，不可新增其他鍵）：",
        "{",
        '  "work_related": bool,',
        f'  "noise_type": one of [{noises}] or null'
        "（work_related=false 時必填，true 時必為 null）,",
        '  "summary": string,',
        '  "entities": [{"type": string, "text": string, '
        '"evidence_message_id": string, "confidence": 0..1}],',
        '  "items": [{'
        f'"type": one of [{types}], '
        f'"domain_code": one of [{domains}], '
        '"event_type_code": string, "title": string, "summary": string, '
        '"owner_text": string or null, '
        '"deadline": {"raw_text": string, "resolved_at": ISO8601 or null, '
        '"timezone": "Asia/Taipei", "confidence": 0..1} or null, '
        '"requires_user_action": bool, '
        '"evidence_message_ids": [string], "confidence": 0..1}],',
        '  "overall_confidence": 0..1',
        "}",
        "",
        "規則：",
        "- evidence_message_ids 只能使用下方訊息的 id，不可自行編造 id。",
        "- 一般閒聊、貼圖、廣告請設 work_related=false 並給 noise_type，items 留空。",
        "- work_related=true 時 items 至少一項；缺貨這類案件應同時給出相關的 "
        "EVENT／TASK／COMMITMENT／RISK。",
        f"- 相對日期（例如「明天」）請以時區 {request.timezone} 依參考時間換算 resolved_at，"
        "並在 raw_text 保留原文。",
        f"- 參考時間：{request.reference_time}",
        "",
        "對話訊息：",
    ]
    for message in request.messages:
        text = (message.text or "").replace("\n", " ").strip()
        lines.append(f"- id={message.id} time={message.source_created_at} 內容：{text}")
    return "\n".join(lines)
