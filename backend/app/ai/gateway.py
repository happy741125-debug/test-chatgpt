from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.providers import AIProvider, AnalysisMessage, AnalysisRequest
from app.ai.schemas import ContextAnalysisOutput
from app.core.logging import correlation_id
from app.models import (
    AIRun,
    AIRunStatus,
    Context,
    ContextMessage,
    ContextStatus,
    Message,
    ProcessingStatus,
    PromptStatus,
    PromptVersion,
)


class AIGatewayError(RuntimeError):
    error_code = "AI_GATEWAY_ERROR"


class AIContextNotFoundError(AIGatewayError):
    error_code = "AI_CONTEXT_NOT_FOUND"


class ActivePromptNotFoundError(AIGatewayError):
    error_code = "AI_ACTIVE_PROMPT_NOT_FOUND"


class AIOutputValidationError(AIGatewayError):
    error_code = "AI_OUTPUT_VALIDATION_FAILED"


class PromptContextBuilder:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def build(self, context_id: str, prompt: PromptVersion) -> AnalysisRequest:
        with self.session_factory() as session:
            context = session.get(Context, context_id)
            if context is None:
                raise AIContextNotFoundError("Context does not exist")
            rows = session.execute(
                select(ContextMessage, Message)
                .join(Message, Message.id == ContextMessage.message_id)
                .where(ContextMessage.context_id == context_id)
                .order_by(ContextMessage.sequence)
            ).all()
            messages = tuple(
                AnalysisMessage(
                    id=message.id,
                    sequence=link.sequence,
                    sender_identity_id=message.sender_identity_id,
                    message_type=message.message_type,
                    text=message.text,
                    source_created_at=_as_utc(message.source_created_at).isoformat(),
                )
                for link, message in rows
            )
            reference_time = _as_utc(context.end_at).astimezone(ZoneInfo("Asia/Taipei"))
            return AnalysisRequest(
                context_id=context.id,
                context_version=context.version,
                timezone="Asia/Taipei",
                reference_time=reference_time.isoformat(),
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                prompt_template=prompt.template_text,
                messages=messages,
            )


class AIGateway:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        provider: AIProvider,
        *,
        prompt_name: str = "context-intelligence",
        low_confidence_threshold: float = 0.75,
    ) -> None:
        self.session_factory = session_factory
        self.provider = provider
        self.prompt_name = prompt_name
        self.low_confidence_threshold = low_confidence_threshold
        self.context_builder = PromptContextBuilder(session_factory)

    def analyze_context(self, context_id: str) -> ContextAnalysisOutput:
        context, prompt, run = self._start_run(context_id)
        request = self.context_builder.build(context.id, prompt)
        raw_output: dict[str, object] | None = None
        started = monotonic()
        try:
            response = self.provider.analyze(request)
            raw_output = response.output
            output = ContextAnalysisOutput.model_validate(raw_output)
            self._validate_evidence(output, {message.id for message in request.messages})
        except (ValidationError, AIOutputValidationError) as exc:
            latency_ms = int((monotonic() - started) * 1000)
            self._fail_run(
                run.id,
                context.id,
                raw_output,
                AIOutputValidationError.error_code,
                latency_ms,
            )
            raise AIOutputValidationError("AI output did not match the required schema") from exc
        except Exception as exc:
            latency_ms = int((monotonic() - started) * 1000)
            self._fail_run(run.id, context.id, raw_output, "AI_PROVIDER_ERROR", latency_ms)
            raise AIGatewayError("AI provider request failed") from exc

        latency_ms = int((monotonic() - started) * 1000)
        requires_review = output.overall_confidence < self.low_confidence_threshold or any(
            item.confidence < self.low_confidence_threshold for item in output.items
        )
        with self.session_factory() as session:
            saved_run = session.get(AIRun, run.id)
            saved_context = session.get(Context, context.id)
            if saved_run is None or saved_context is None:
                raise AIGatewayError("AI run state disappeared")
            saved_run.status = AIRunStatus.SUCCEEDED.value
            saved_run.raw_response_json = raw_output
            saved_run.validated_output_json = output.model_dump(mode="json")
            saved_run.overall_confidence = output.overall_confidence
            saved_run.requires_review = requires_review
            saved_run.input_tokens = response.input_tokens
            saved_run.output_tokens = response.output_tokens
            saved_run.estimated_cost_microunits = response.estimated_cost_microunits
            saved_run.latency_ms = latency_ms
            saved_run.completed_at = datetime.now(UTC)
            saved_context.status = ContextStatus.ANALYZED.value
            message_ids = [message.id for message in request.messages]
            if message_ids:
                for message in session.scalars(select(Message).where(Message.id.in_(message_ids))):
                    message.processing_status = ProcessingStatus.PROCESSED.value
            session.commit()
        return output

    def _start_run(self, context_id: str) -> tuple[Context, PromptVersion, AIRun]:
        with self.session_factory() as session:
            context = session.get(Context, context_id)
            if context is None:
                raise AIContextNotFoundError("Context does not exist")
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
                raise ActivePromptNotFoundError("No active prompt version")
            context.status = ContextStatus.ANALYZING.value
            run = AIRun(
                context_id=context.id,
                context_version=context.version,
                prompt_version_id=prompt.id,
                provider=self.provider.name,
                model=self.provider.model,
                status=AIRunStatus.RUNNING.value,
                correlation_id=correlation_id.get(),
            )
            session.add(run)
            session.commit()
            return context, prompt, run

    def _fail_run(
        self,
        run_id: str,
        context_id: str,
        raw_output: dict[str, object] | None,
        error_code: str,
        latency_ms: int,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(AIRun, run_id)
            context = session.get(Context, context_id)
            if run is not None:
                run.status = AIRunStatus.FAILED.value
                run.raw_response_json = raw_output
                run.error_code = error_code
                run.error_message = "AI analysis failed; inspect the error code and stored run."
                run.latency_ms = latency_ms
                run.completed_at = datetime.now(UTC)
            if context is not None:
                context.status = ContextStatus.FAILED.value
            session.commit()

    @staticmethod
    def _validate_evidence(output: ContextAnalysisOutput, allowed_message_ids: set[str]) -> None:
        referenced = {
            evidence_id
            for item in output.items
            for evidence_id in item.evidence_message_ids
        }
        referenced.update(entity.evidence_message_id for entity in output.entities)
        if not referenced.issubset(allowed_message_ids):
            raise AIOutputValidationError("Output referenced messages outside this context")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
