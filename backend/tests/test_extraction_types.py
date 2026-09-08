from __future__ import annotations

from app.ai.providers import AnalysisMessage, AnalysisRequest, RuleBasedAIProvider
from app.ai.schemas import ContextAnalysisOutput
from app.intelligence.materializer import _needs_human_review


def _request(text: str) -> AnalysisRequest:
    return AnalysisRequest(
        context_id="ctx-types",
        context_version=1,
        timezone="Asia/Taipei",
        reference_time="2026-09-08T12:00:00+08:00",
        prompt_name="context-intelligence",
        prompt_version=1,
        prompt_template="Return schema v1.",
        messages=(
            AnalysisMessage(
                id="m-1",
                sequence=1,
                sender_identity_id="identity-1",
                message_type="text",
                text=text,
                source_created_at="2026-09-08T04:00:00+00:00",
            ),
        ),
    )


def _analyze(text: str) -> ContextAnalysisOutput:
    response = RuleBasedAIProvider().analyze(_request(text))
    return ContextAnalysisOutput.model_validate(response.output)


def test_rule_provider_emits_decision_required() -> None:
    output = _analyze("這張大單利潤很薄，要不要接？請老闆決定。")
    assert output.work_related is True
    types = {item.type.value for item in output.items}
    assert "DECISION_REQUIRED" in types
    decision = next(item for item in output.items if item.type.value == "DECISION_REQUIRED")
    assert decision.requires_user_action is True
    # Decisions are deliberately low-confidence so they route to a human.
    assert decision.confidence < 0.75


def test_rule_provider_emits_follow_up() -> None:
    output = _analyze("客訴這件先記著，後續再跟進客戶回覆。")
    assert {item.type.value for item in output.items} & {"FOLLOW_UP"}
    follow = next(item for item in output.items if item.type.value == "FOLLOW_UP")
    assert follow.requires_user_action is False


def test_rule_provider_emits_fyi() -> None:
    # FYI is an informational note attached to a detected operational event.
    output = _analyze("供參：本週缺貨情況週報已更新，請知會相關同仁。")
    assert "FYI" in {item.type.value for item in output.items}


def test_plain_chat_still_noise() -> None:
    output = _analyze("大家早安，今天天氣不錯。")
    assert output.work_related is False
    assert output.items == []


def test_deidentified_operational_phrasings_hit_expected_categories() -> None:
    # All examples are synthetic or rewritten and contain no customer data.
    cases = [
        ("測試貨件剛送達，請協助開立入庫單。", "INBOUND_OPERATION"),
        ("測試客戶要使用新系統，請協助串接與帳號設定。", "SYSTEM_ONBOARDING"),
        ("請提供每板租金與每趟運費的測試報價。", "QUOTE_REQUEST"),
        ("測試合約已收到，請提供保證金付款資訊。", "CONTRACT_PROGRESS"),
        ("測試商品需要換貨，請問是否要開出貨單？", "RETURN_EXCHANGE"),
        ("測試貨件已送達，但內容物有缺。", "SHIPMENT_DISCREPANCY"),
        ("有一筆測試訂單比較急，能否趕在今天寄出？", "URGENT_ORDER"),
        ("本月帳款已收到，但上月帳款尚未收到。", "PAYMENT_STATUS"),
    ]
    for text, expected in cases:
        output = _analyze(text)
        codes = {item.event_type_code for item in output.items}
        assert expected in codes, f"{text!r} -> {codes}, expected {expected}"


def test_shipment_discrepancy_is_treated_as_risk() -> None:
    output = _analyze("貨件上午送到，對方說裡面內容物有缺，滿急的請盡快確認")
    assert "RISK" in {item.type.value for item in output.items}


def test_inbound_and_outbound_stages_keep_their_own_meaning() -> None:
    inbound = _analyze("今日已入庫，謝謝。")
    assert {item.event_type_code for item in inbound.items} == {"INBOUND_OPERATION"}

    output = _analyze("已入庫，訂單麻煩重新整理庫存，我們今日就會安排出貨。")
    codes = {item.event_type_code for item in output.items}
    assert codes == {"INBOUND_OPERATION", "OUTBOUND_OPERATION"}


def test_operational_closure_is_an_fyi_announcement() -> None:
    output = _analyze("因天候影響，明日停班停課，倉庫暫停收貨與出貨作業。")
    assert output.work_related is True
    assert "OPERATIONAL_ANNOUNCEMENT" in {item.event_type_code for item in output.items}
    assert "FYI" in {item.type.value for item in output.items}


def test_needs_human_review_rule() -> None:
    # High priority + not-very-confident -> must be reviewed by a human.
    assert _needs_human_review("P0", 0.85) is True
    assert _needs_human_review("P1", 0.89) is True
    # High priority but highly confident -> may skip review.
    assert _needs_human_review("P1", 0.95) is False
    # Lower priority is governed by the gateway's general threshold, not this rule.
    assert _needs_human_review("P2", 0.5) is False
    assert _needs_human_review("P3", 0.5) is False
