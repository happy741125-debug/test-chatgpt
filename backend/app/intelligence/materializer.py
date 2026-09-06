from __future__ import annotations

from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.schemas import ContextAnalysisOutput
from app.intelligence.priority import calculate_priority
from app.models import (
    AIRun,
    AIRunStatus,
    Context,
    IntelligenceObject,
    IntelligenceSource,
)


class IntelligenceMaterializer:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def materialize(self, context_id: str, output: ContextAnalysisOutput) -> list[str]:
        if not output.work_related:
            return []
        with self.session_factory() as session:
            context = session.get(Context, context_id)
            if context is None:
                raise ValueError("Context does not exist")
            run = session.scalar(
                select(AIRun)
                .where(
                    AIRun.context_id == context_id,
                    AIRun.context_version == context.version,
                    AIRun.status == AIRunStatus.SUCCEEDED.value,
                )
                .order_by(AIRun.created_at.desc())
                .limit(1)
            )
            if run is None:
                raise ValueError("Successful AI run does not exist")

            created_ids: list[str] = []
            for item in output.items:
                fingerprint = _fingerprint(
                    item.type.value,
                    item.domain_code.value,
                    item.event_type_code,
                    item.title,
                )
                existing = session.scalar(
                    select(IntelligenceObject.id).where(
                        IntelligenceObject.context_id == context_id,
                        IntelligenceObject.context_version == context.version,
                        IntelligenceObject.fingerprint == fingerprint,
                    )
                )
                if existing is not None:
                    created_ids.append(existing)
                    continue
                priority = calculate_priority(item)
                intelligence = IntelligenceObject(
                    context_id=context_id,
                    context_version=context.version,
                    ai_run_id=run.id,
                    fingerprint=fingerprint,
                    type=item.type.value,
                    domain_code=item.domain_code.value,
                    event_type_code=item.event_type_code,
                    title=item.title,
                    summary=item.summary,
                    owner_text=item.owner_text,
                    deadline_at=item.deadline.resolved_at if item.deadline else None,
                    deadline_raw_text=item.deadline.raw_text if item.deadline else None,
                    requires_user_action=item.requires_user_action,
                    confidence=item.confidence,
                    priority_score=priority.score,
                    priority_level=priority.level,
                    priority_reasons_json=priority.reasons,
                    requires_review=run.requires_review,
                )
                session.add(intelligence)
                session.flush()
                for order, message_id in enumerate(item.evidence_message_ids, start=1):
                    session.add(
                        IntelligenceSource(
                            intelligence_id=intelligence.id,
                            context_id=context_id,
                            message_id=message_id,
                            evidence_order=order,
                        )
                    )
                created_ids.append(intelligence.id)
            session.commit()
            return created_ids


class IntelligencePipeline:
    def __init__(self, gateway, materializer: IntelligenceMaterializer) -> None:  # type: ignore[no-untyped-def]
        self.gateway = gateway
        self.materializer = materializer

    def __call__(self, context_id: str) -> list[str]:
        output = self.gateway.analyze_context(context_id)
        return self.materializer.materialize(context_id, output)


def _fingerprint(item_type: str, domain: str, event_type: str, title: str) -> str:
    canonical = "|".join((item_type, domain, event_type, " ".join(title.lower().split())))
    return sha256(canonical.encode("utf-8")).hexdigest()
