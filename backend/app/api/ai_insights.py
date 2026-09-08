from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import ExtractionComparison

router = APIRouter(prefix="/api/ai", tags=["ai-insights"])


class ComparisonSummary(BaseModel):
    total: int
    agree: int
    partial: int
    disagree: int
    shadow_failed: int
    agreement_rate: float | None = Field(
        default=None,
        description="AGREE 佔已成功比對（不含 shadow_failed）的比例，尚無資料時為 null。",
    )


class ComparisonRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    context_id: str
    context_version: int
    agreement: str
    primary_provider: str
    shadow_provider: str
    shadow_model: str
    shadow_status: str
    shadow_error_code: str | None
    shadow_latency_ms: int | None
    shadow_cost_microunits: int | None
    diff_json: dict[str, object]
    created_at: datetime


@router.get("/comparisons/summary")
def comparison_summary(_: OpsAccess, session: SessionDependency) -> ComparisonSummary:
    rows = session.execute(
        select(ExtractionComparison.agreement, func.count()).group_by(
            ExtractionComparison.agreement
        )
    ).all()
    counts = {agreement: count for agreement, count in rows}
    agree = counts.get("AGREE", 0)
    partial = counts.get("PARTIAL", 0)
    disagree = counts.get("DISAGREE", 0)
    shadow_failed = counts.get("SHADOW_FAILED", 0)
    total = agree + partial + disagree + shadow_failed
    scored = agree + partial + disagree
    return ComparisonSummary(
        total=total,
        agree=agree,
        partial=partial,
        disagree=disagree,
        shadow_failed=shadow_failed,
        agreement_rate=round(agree / scored, 3) if scored else None,
    )


@router.get("/comparisons")
def list_comparisons(
    _: OpsAccess,
    session: SessionDependency,
    agreement: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ComparisonRow]:
    query = select(ExtractionComparison)
    if agreement:
        query = query.where(ExtractionComparison.agreement == agreement)
    rows = session.scalars(
        query.order_by(ExtractionComparison.created_at.desc()).limit(limit)
    ).all()
    return [ComparisonRow.model_validate(row) for row in rows]
