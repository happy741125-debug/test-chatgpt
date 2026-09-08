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


def test_needs_human_review_rule() -> None:
    # High priority + not-very-confident -> must be reviewed by a human.
    assert _needs_human_review("P0", 0.85) is True
    assert _needs_human_review("P1", 0.89) is True
    # High priority but highly confident -> may skip review.
    assert _needs_human_review("P1", 0.95) is False
    # Lower priority is governed by the gateway's general threshold, not this rule.
    assert _needs_human_review("P2", 0.5) is False
    assert _needs_human_review("P3", 0.5) is False
