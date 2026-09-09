from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import (
    AIRun,
    Attachment,
    AttachmentAccessAudit,
    CaseReviewItem,
    Context,
    ContextMessage,
    IntelligenceChangeAudit,
    IntelligenceFeedback,
    IntelligenceHistoryEvent,
    IntelligenceObject,
    IntelligenceSource,
    IntelligenceStatusAudit,
    Message,
    ProcessingJob,
    RawEvent,
    WeeklyReviewSnapshot,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

CONFIRM_PHRASE = "CLEAR-TEST-DATA"

# Cleared child-first so foreign keys stay satisfied on PostgreSQL. This removes
# only the LINE/Gmail intelligence pipeline test data. Configuration (domains,
# event types, prompts, channels), manual weekly reviews, executive metrics and
# revenue/operations/GoWarehouse imports are intentionally KEPT.
_RESET_ORDER = (
    ("intelligence_history_events", IntelligenceHistoryEvent),
    ("intelligence_status_audits", IntelligenceStatusAudit),
    ("intelligence_change_audits", IntelligenceChangeAudit),
    ("intelligence_feedback", IntelligenceFeedback),
    ("case_review_items", CaseReviewItem),
    ("intelligence_sources", IntelligenceSource),
    ("intelligence_objects", IntelligenceObject),
    ("ai_runs", AIRun),
    ("weekly_review_snapshots", WeeklyReviewSnapshot),
    ("context_messages", ContextMessage),
    ("attachment_access_audits", AttachmentAccessAudit),
    ("attachments", Attachment),
    ("contexts", Context),
    ("messages", Message),
    ("raw_events", RawEvent),
    ("processing_jobs", ProcessingJob),
)


class ResetRequest(BaseModel):
    confirm: str = ""


class ResetResult(BaseModel):
    deleted: dict[str, int]
    total_deleted: int


@router.post("/reset-intelligence")
def reset_intelligence(
    payload: ResetRequest,
    _: OpsAccess,
    session: SessionDependency,
) -> ResetResult:
    """Clear intelligence-pipeline test data. Requires the exact confirm phrase
    so it can never fire by accident."""
    if payload.confirm != CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "CONFIRMATION_REQUIRED",
                "message": f"請輸入確認字串「{CONFIRM_PHRASE}」以清除情報測試資料。",
            },
        )
    deleted: dict[str, int] = {}
    for name, model in _RESET_ORDER:
        count = session.scalar(select(func.count()).select_from(model)) or 0
        if count:
            session.execute(delete(model))
        deleted[name] = int(count)
    session.commit()
    return ResetResult(deleted=deleted, total_deleted=sum(deleted.values()))
