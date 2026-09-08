from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ai.gemini import GeminiAIProvider
from app.ai.openai import OpenAIAIProvider
from app.ai.prompt import build_extraction_prompt
from app.ai.providers import AnalysisMessage, AnalysisRequest, MockAIProvider
from app.ai.schemas import ContextAnalysisOutput
from app.ai.shadow import (
    ShadowComparator,
    ShadowExtractionPipeline,
    build_shadow_provider,
)
from app.core.config import Settings
from app.models import (
    Context,
    ContextMessage,
    ExtractionComparison,
    Message,
    Platform,
    PromptStatus,
    PromptVersion,
)
from app.worker import build_context_pipeline

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}
MESSAGE_ID = "m-shadow-1"
CONTEXT_ID = "ctx-shadow-1"


def _analysis_request() -> AnalysisRequest:
    return AnalysisRequest(
        context_id=CONTEXT_ID,
        context_version=1,
        timezone="Asia/Taipei",
        reference_time="2026-09-08T12:00:00+08:00",
        prompt_name="context-intelligence",
        prompt_version=1,
        prompt_template="Return schema v1.",
        messages=(
            AnalysisMessage(
                id=MESSAGE_ID,
                sequence=1,
                sender_identity_id="identity-1",
                message_type="text",
                text="ORD-123 缺貨 20 箱，Kevin 已請廠商補，明天下午到。",
                source_created_at="2026-09-08T04:00:00+00:00",
            ),
        ),
    )


def _gemini_response(payload_json: str) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": payload_json}]}}],
        "usageMetadata": {"promptTokenCount": 320, "candidatesTokenCount": 110},
    }


def _output_dict(*, work_related=True, items=None, noise_type=None) -> dict:
    if items is None:
        items = [("EVENT", "STOCK_SHORTAGE")]
    return {
        "work_related": work_related,
        "noise_type": noise_type,
        "summary": "測試摘要。",
        "entities": [],
        "items": [
            {
                "type": item_type,
                "domain_code": "WAREHOUSE_OPERATIONS",
                "event_type_code": event_code,
                "title": f"{item_type} {event_code}",
                "summary": "測試項目。",
                "owner_text": None,
                "deadline": None,
                "requires_user_action": False,
                "evidence_message_ids": [MESSAGE_ID],
                "confidence": 0.9,
            }
            for item_type, event_code in items
        ],
        "overall_confidence": 0.9,
    }


# --------------------------------------------------------------------------- #
# GeminiAIProvider (no network — invoke is injected)
# --------------------------------------------------------------------------- #
def test_gemini_provider_parses_structured_output() -> None:
    import json

    captured: dict[str, object] = {}

    def fake_invoke(url: str, headers: dict[str, str], body: dict) -> dict:
        captured["url"] = url
        captured["headers"] = headers
        return _gemini_response(json.dumps(_output_dict()))

    provider = GeminiAIProvider("secret-key", model="gemini-2.5-flash", invoke=fake_invoke)
    response = provider.analyze(_analysis_request())

    output = ContextAnalysisOutput.model_validate(response.output)
    assert output.work_related is True
    assert {item.type.value for item in output.items} == {"EVENT"}
    assert response.input_tokens == 320
    assert response.output_tokens == 110
    assert response.estimated_cost_microunits and response.estimated_cost_microunits > 0
    # The API key must travel in a header, never in the URL.
    assert "secret-key" not in captured["url"]  # type: ignore[operator]
    assert captured["headers"]["x-goog-api-key"] == "secret-key"  # type: ignore[index]


def test_extraction_prompt_lists_message_ids_and_reference_time() -> None:
    prompt = build_extraction_prompt(_analysis_request())
    assert MESSAGE_ID in prompt
    assert "2026-09-08T12:00:00+08:00" in prompt
    assert "work_related" in prompt


def test_openai_provider_parses_structured_output() -> None:
    import json

    captured: dict[str, object] = {}

    def fake_invoke(url: str, headers: dict[str, str], body: dict) -> dict:
        captured["headers"] = headers
        captured["model"] = body["model"]
        return {
            "choices": [{"message": {"content": json.dumps(_output_dict())}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 90},
        }

    provider = OpenAIAIProvider("sk-secret", model="gpt-4o-mini", invoke=fake_invoke)
    response = provider.analyze(_analysis_request())

    output = ContextAnalysisOutput.model_validate(response.output)
    assert {item.type.value for item in output.items} == {"EVENT"}
    assert response.input_tokens == 300
    assert response.output_tokens == 90
    assert captured["headers"]["Authorization"] == "Bearer sk-secret"  # type: ignore[index]
    assert captured["model"] == "gpt-4o-mini"


# --------------------------------------------------------------------------- #
# ShadowComparator
# --------------------------------------------------------------------------- #
def _seed_context(database) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
    with database.session_factory() as session:
        session.add_all(
            [
                Context(
                    id=CONTEXT_ID,
                    channel_id="channel-shadow",
                    start_at=now,
                    end_at=now + timedelta(minutes=5),
                    version=1,
                ),
                Message(
                    id=MESSAGE_ID,
                    platform=Platform.LINE.value,
                    external_message_id="ext-shadow-1",
                    raw_event_id="raw-shadow-1",
                    channel_id="channel-shadow",
                    conversation_id="conv-shadow-1",
                    message_type="text",
                    text="ORD-123 缺貨 20 箱。",
                    source_created_at=now,
                ),
                PromptVersion(
                    name="context-intelligence",
                    version=1,
                    template_text="Return structured intelligence.",
                    output_schema_version="v1",
                    status=PromptStatus.ACTIVE.value,
                    activated_at=now,
                ),
            ]
        )
        session.flush()
        session.add(
            ContextMessage(context_id=CONTEXT_ID, message_id=MESSAGE_ID, sequence=1)
        )
        session.commit()


def _comparator(database, shadow_provider) -> ShadowComparator:  # type: ignore[no-untyped-def]
    return ShadowComparator(
        database.session_factory,
        shadow_provider,
        primary_provider_name="rule-based",
        primary_model="rule-based-v1",
    )


def _stored_comparison(database) -> ExtractionComparison:  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    with database.session_factory() as session:
        record = session.scalar(select(ExtractionComparison))
        assert record is not None
        session.expunge(record)
        return record


def test_shadow_records_agreement_when_outputs_match(test_context) -> None:
    _, database, _ = test_context
    _seed_context(database)
    primary = ContextAnalysisOutput.model_validate(_output_dict())
    shadow_provider = MockAIProvider(_output_dict())

    _comparator(database, shadow_provider).compare(CONTEXT_ID, primary)

    record = _stored_comparison(database)
    assert record.agreement == "AGREE"
    assert record.shadow_status == "SUCCEEDED"
    assert record.shadow_provider == "mock"
    assert record.shadow_output_json is not None


def test_shadow_records_partial_when_types_overlap(test_context) -> None:
    _, database, _ = test_context
    _seed_context(database)
    primary = ContextAnalysisOutput.model_validate(
        _output_dict(items=[("EVENT", "STOCK_SHORTAGE"), ("TASK", "REPLENISHMENT")])
    )
    shadow_provider = MockAIProvider(_output_dict(items=[("EVENT", "STOCK_SHORTAGE")]))

    _comparator(database, shadow_provider).compare(CONTEXT_ID, primary)

    record = _stored_comparison(database)
    assert record.agreement == "PARTIAL"
    assert record.diff_json["item_types"]["primary_only"] == ["TASK"]


def test_shadow_failure_is_recorded_not_raised(test_context) -> None:
    _, database, _ = test_context
    _seed_context(database)
    primary = ContextAnalysisOutput.model_validate(_output_dict())

    class RaisingProvider:
        name = "gemini"
        model = "gemini-2.5-flash"

        def analyze(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("gemini timed out")

    # Must not raise.
    _comparator(database, RaisingProvider()).compare(CONTEXT_ID, primary)

    record = _stored_comparison(database)
    assert record.agreement == "SHADOW_FAILED"
    assert record.shadow_status == "FAILED"
    assert record.shadow_error_code == "RuntimeError"
    assert record.shadow_output_json is None


def test_shadow_rejects_evidence_outside_context(test_context) -> None:
    _, database, _ = test_context
    _seed_context(database)
    primary = ContextAnalysisOutput.model_validate(_output_dict())
    invalid = _output_dict()
    invalid["items"][0]["evidence_message_ids"] = ["message-not-in-context"]
    shadow_provider = MockAIProvider(invalid)

    _comparator(database, shadow_provider).compare(CONTEXT_ID, primary)

    record = _stored_comparison(database)
    assert record.agreement == "SHADOW_FAILED"
    assert record.shadow_status == "FAILED"


# --------------------------------------------------------------------------- #
# Wiring + API
# --------------------------------------------------------------------------- #
def test_build_pipeline_selects_shadow_when_active(test_context) -> None:
    _, database, queue = test_context
    settings = Settings(
        ai_provider="rule-based",
        shadow_enabled=True,
        gemini_api_key="fake-key",
    )
    handler = build_context_pipeline(settings, database, queue)
    assert isinstance(handler.analysis_handler, ShadowExtractionPipeline)


def test_build_pipeline_skips_shadow_without_key(test_context) -> None:
    _, database, queue = test_context
    settings = Settings(
        ai_provider="rule-based",
        shadow_enabled=True,
        gemini_api_key="",
    )
    handler = build_context_pipeline(settings, database, queue)
    assert not isinstance(handler.analysis_handler, ShadowExtractionPipeline)


def test_shadow_provider_switches_to_openai() -> None:
    settings = Settings(
        ai_provider="rule-based",
        shadow_enabled=True,
        shadow_provider="openai",
        openai_api_key="sk-key",
        openai_model="gpt-4o-mini",
    )
    assert settings.shadow_active is True
    assert settings.shadow_api_key == "sk-key"
    provider = build_shadow_provider(settings)
    assert isinstance(provider, OpenAIAIProvider)
    assert provider.name == "openai"
    assert provider.model == "gpt-4o-mini"


def test_shadow_provider_defaults_to_gemini() -> None:
    settings = Settings(
        ai_provider="rule-based",
        shadow_enabled=True,
        gemini_api_key="g-key",
    )
    provider = build_shadow_provider(settings)
    assert isinstance(provider, GeminiAIProvider)
    assert provider.name == "gemini"


def test_openai_selected_but_missing_key_is_inactive() -> None:
    settings = Settings(
        ai_provider="rule-based",
        shadow_enabled=True,
        shadow_provider="openai",
        openai_api_key="",
    )
    assert settings.shadow_active is False


def test_comparison_api_summary_and_list(test_context) -> None:
    client, database, _ = test_context
    _seed_context(database)
    _comparator(database, MockAIProvider(_output_dict())).compare(
        CONTEXT_ID, ContextAnalysisOutput.model_validate(_output_dict())
    )

    summary = client.get("/api/ai/comparisons/summary", headers=OPS_HEADERS)
    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    assert summary.json()["agree"] == 1
    assert summary.json()["agreement_rate"] == 1.0

    listing = client.get("/api/ai/comparisons", headers=OPS_HEADERS)
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["agreement"] == "AGREE"


def test_comparison_api_requires_ops_token(test_context) -> None:
    client, _, _ = test_context
    assert client.get("/api/ai/comparisons/summary").status_code == 403
