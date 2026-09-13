from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import (
    AdminCredential,
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
from app.security.password import hash_password, verify_password

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


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    _: OpsAccess,
    session: SessionDependency,
) -> dict[str, bool]:
    """Set an admin password. The env OPS_API_TOKEN stays valid as recovery."""
    settings = request.app.state.settings
    stored = session.get(AdminCredential, "singleton")
    current_ok = bool(
        settings.ops_api_token
        and hmac.compare_digest(payload.current_password, settings.ops_api_token)
    ) or bool(stored and verify_password(payload.current_password, stored.password_hash))
    if not current_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "CURRENT_PASSWORD_INVALID", "message": "目前密碼不正確。"},
        )
    new_hash = hash_password(payload.new_password)
    if stored is None:
        session.add(AdminCredential(id="singleton", password_hash=new_hash))
    else:
        stored.password_hash = new_hash
    session.commit()
    return {"ok": True}


class AiSummaryConfig(BaseModel):
    provider: str  # "gemini" | "openai"
    model: str
    shadow_enabled: bool
    shadow_active: bool
    key_configured: bool
    key_env_var: str
    primary_provider: str
    summary_mode: str


@router.get("/ai-config")
def ai_config(request: Request, _: OpsAccess) -> AiSummaryConfig:
    """Read-only status of the LLM 白話摘要 setup.

    Never returns the API key itself — only whether one is configured. The key is
    set as a Render environment variable, never entered through the web UI or stored
    in the database.
    """
    settings = request.app.state.settings
    is_openai = settings.shadow_provider == "openai"
    model = settings.openai_model if is_openai else settings.gemini_model
    key_configured = bool(settings.openai_api_key if is_openai else settings.gemini_api_key)
    key_env_var = "OPENAI_API_KEY" if is_openai else "GEMINI_API_KEY"
    if settings.ai_provider in ("gemini", "openai"):
        summary_mode = "白話摘要已升為主力"
    elif settings.shadow_active:
        summary_mode = "影子模式（比對中，未影響正式卡片）"
    elif settings.shadow_enabled and not key_configured:
        summary_mode = "影子模式已開，但金鑰未設定"
    else:
        summary_mode = "規則版（預設）"
    return AiSummaryConfig(
        provider=settings.shadow_provider,
        model=model,
        shadow_enabled=settings.shadow_enabled,
        shadow_active=settings.shadow_active,
        key_configured=key_configured,
        key_env_var=key_env_var,
        primary_provider=settings.ai_provider,
        summary_mode=summary_mode,
    )
