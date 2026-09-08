from __future__ import annotations

import logging
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.gateway import AIGateway, PromptContextBuilder
from app.ai.providers import AIProvider, AnalysisRequest
from app.ai.schemas import ContextAnalysisOutput
from app.intelligence.materializer import IntelligenceMaterializer
from app.models import (
    ComparisonAgreement,
    ExtractionComparison,
    PromptStatus,
    PromptVersion,
)

logger = logging.getLogger(__name__)


class ShadowComparator:
    """Runs the LLM on the same context and records a comparison. Never raises."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        shadow_provider: AIProvider,
        *,
        primary_provider_name: str,
        primary_model: str,
        prompt_name: str = "context-intelligence",
    ) -> None:
        self.session_factory = session_factory
        self.shadow_provider = shadow_provider
        self.primary_provider_name = primary_provider_name
        self.primary_model = primary_model
        self.prompt_name = prompt_name
        self.context_builder = PromptContextBuilder(session_factory)

    def compare(self, context_id: str, primary_output: ContextAnalysisOutput) -> None:
        try:
            request = self._build_request(context_id)
        except Exception:  # noqa: BLE001 - shadow mode must never break the primary path
            logger.warning("Shadow request build failed", extra={"context_id": context_id})
            return

        allowed_ids = {message.id for message in request.messages}
        shadow_output: ContextAnalysisOutput | None = None
        status = "SUCCEEDED"
        error_code: str | None = None
        cost: int | None = None
        started = monotonic()
        try:
            response = self.shadow_provider.analyze(request)
            shadow_output = ContextAnalysisOutput.model_validate(response.output)
            _ensure_evidence_in_context(shadow_output, allowed_ids)
            cost = response.estimated_cost_microunits
        except Exception as exc:  # noqa: BLE001 - record the failure, do not propagate
            status = "FAILED"
            error_code = type(exc).__name__
            logger.warning(
                "Shadow extraction failed",
                extra={"context_id": context_id, "error": error_code},
            )
        latency_ms = int((monotonic() - started) * 1000)

        agreement, diff = _compare_outputs(primary_output, shadow_output, status)
        self._persist(
            context_id=context_id,
            context_version=request.context_version,
            primary_output=primary_output,
            shadow_output=shadow_output,
            status=status,
            error_code=error_code,
            latency_ms=latency_ms,
            cost=cost,
            agreement=agreement,
            diff=diff,
        )

    def _build_request(self, context_id: str) -> AnalysisRequest:
        with self.session_factory() as session:
            prompt = session.scalar(
                select(PromptVersion)
                .where(
                    PromptVersion.name == self.prompt_name,
                    PromptVersion.status == PromptStatus.ACTIVE.value,
                )
                .order_by(PromptVersion.version.desc())
                .limit(1)
            )
            if prompt is None:
                raise ValueError("No active prompt version for shadow run")
        return self.context_builder.build(context_id, prompt)

    def _persist(
        self,
        *,
        context_id: str,
        context_version: int,
        primary_output: ContextAnalysisOutput,
        shadow_output: ContextAnalysisOutput | None,
        status: str,
        error_code: str | None,
        latency_ms: int | None,
        cost: int | None,
        agreement: str,
        diff: dict[str, object],
    ) -> None:
        with self.session_factory() as session:
            record = session.scalar(
                select(ExtractionComparison).where(
                    ExtractionComparison.context_id == context_id,
                    ExtractionComparison.context_version == context_version,
                )
            )
            if record is None:
                record = ExtractionComparison(
                    context_id=context_id,
                    context_version=context_version,
                )
                session.add(record)
            record.primary_provider = self.primary_provider_name
            record.primary_model = self.primary_model
            record.primary_output_json = primary_output.model_dump(mode="json")
            record.shadow_provider = self.shadow_provider.name
            record.shadow_model = self.shadow_provider.model
            record.shadow_status = status
            record.shadow_error_code = error_code
            record.shadow_output_json = (
                shadow_output.model_dump(mode="json") if shadow_output is not None else None
            )
            record.shadow_latency_ms = latency_ms
            record.shadow_cost_microunits = cost
            record.agreement = agreement
            record.diff_json = diff
            session.commit()


class ShadowExtractionPipeline:
    """Primary rule-based extraction produces the cards; the LLM only shadows it."""

    def __init__(
        self,
        gateway: AIGateway,
        materializer: IntelligenceMaterializer,
        comparator: ShadowComparator,
    ) -> None:
        self.gateway = gateway
        self.materializer = materializer
        self.comparator = comparator

    def __call__(self, context_id: str) -> list[str]:
        output = self.gateway.analyze_context(context_id)
        intelligence_ids = self.materializer.materialize(context_id, output)
        self.comparator.compare(context_id, output)
        return intelligence_ids


def _ensure_evidence_in_context(
    output: ContextAnalysisOutput, allowed_message_ids: set[str]
) -> None:
    referenced = {
        evidence_id for item in output.items for evidence_id in item.evidence_message_ids
    }
    referenced.update(entity.evidence_message_id for entity in output.entities)
    if not referenced.issubset(allowed_message_ids):
        raise ValueError("Shadow output referenced messages outside this context")


def _compare_outputs(
    primary: ContextAnalysisOutput,
    shadow: ContextAnalysisOutput | None,
    status: str,
) -> tuple[str, dict[str, object]]:
    if status != "SUCCEEDED" or shadow is None:
        return ComparisonAgreement.SHADOW_FAILED.value, {"reason": "shadow_failed"}

    primary_types = {item.type.value for item in primary.items}
    shadow_types = {item.type.value for item in shadow.items}
    primary_events = {item.event_type_code for item in primary.items}
    shadow_events = {item.event_type_code for item in shadow.items}
    diff: dict[str, object] = {
        "work_related": {"primary": primary.work_related, "shadow": shadow.work_related},
        "item_types": {
            "both": sorted(primary_types & shadow_types),
            "primary_only": sorted(primary_types - shadow_types),
            "shadow_only": sorted(shadow_types - primary_types),
        },
        "event_types": {
            "both": sorted(primary_events & shadow_events),
            "primary_only": sorted(primary_events - shadow_events),
            "shadow_only": sorted(shadow_events - primary_events),
        },
        "item_count": {"primary": len(primary.items), "shadow": len(shadow.items)},
        "overall_confidence": {
            "primary": primary.overall_confidence,
            "shadow": shadow.overall_confidence,
        },
    }

    if primary.work_related != shadow.work_related:
        return ComparisonAgreement.DISAGREE.value, diff
    if not primary.work_related and not shadow.work_related:
        return ComparisonAgreement.AGREE.value, diff
    if primary_types == shadow_types and primary_events == shadow_events:
        return ComparisonAgreement.AGREE.value, diff
    if primary_types & shadow_types:
        return ComparisonAgreement.PARTIAL.value, diff
    return ComparisonAgreement.DISAGREE.value, diff
