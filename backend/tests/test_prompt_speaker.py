from __future__ import annotations

from app.ai.prompt import build_extraction_prompt
from app.ai.providers import AnalysisMessage, AnalysisRequest


def _request(sender: str | None) -> AnalysisRequest:
    return AnalysisRequest(
        context_id="ctx-1",
        context_version=1,
        timezone="Asia/Taipei",
        reference_time="2026-09-21T12:00:00+08:00",
        prompt_name="context-intelligence",
        prompt_version=1,
        prompt_template="Return schema v1.",
        messages=(
            AnalysisMessage(
                id="m1",
                sequence=1,
                sender_identity_id="idn-1",
                message_type="text",
                text="缺貨了，明天補",
                source_created_at="2026-09-21T04:00:00+00:00",
                sender=sender,
            ),
        ),
    )


def test_prompt_includes_named_speaker() -> None:
    prompt = build_extraction_prompt(_request("甲廠商"))
    assert "發言者=甲廠商" in prompt
    # Prompt instructs the model to attribute who said/owns what.
    assert "誰" in prompt


def test_prompt_falls_back_to_unknown_speaker() -> None:
    prompt = build_extraction_prompt(_request(None))
    assert "發言者=未知發言者" in prompt


def test_prompt_asks_for_whole_conversation_digest() -> None:
    prompt = build_extraction_prompt(_request("甲廠商"))
    # Summary must be a digest of the whole conversation, not a per-message paraphrase.
    assert "重點總結" in prompt
    assert "不要一則一則" in prompt
    assert "待辦" in prompt or "提醒" in prompt
