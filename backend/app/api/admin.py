from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
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
    WorkCalendarSetting,
)
from app.security.password import hash_password, verify_password
from app.services.line_profile import LineProfileClient
from app.services.name_resolution import resolve_pending_line_names
from app.services.work_calendar import DEFAULT_CLOSED_WEEKDAYS

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


class LineNameResult(BaseModel):
    found: int = 0
    checked: int
    resolved: int


@router.post("/resolve-line-names")
def resolve_line_names(
    request: Request,
    _: OpsAccess,
    session: SessionDependency,
) -> LineNameResult:
    """Fetch real display names for LINE members from LINE's Messaging API.

    Uses the LINE channel access token already set on the server; the token is
    never entered through the web UI. Names that resolve are stored so they show
    everywhere; unresolved members keep their de-identified label.
    """
    token = request.app.state.settings.line_channel_access_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "LINE_TOKEN_MISSING",
                "message": "尚未設定 LINE 存取權杖（LINE_CHANNEL_ACCESS_TOKEN）。",
            },
        )
    result = resolve_pending_line_names(session, LineProfileClient(token))
    return LineNameResult(**result)


class WorkCalendarPayload(BaseModel):
    closed_weekdays: list[int] = Field(max_length=7)
    holiday_dates: list[date] = Field(default_factory=list, max_length=366)
    working_dates: list[date] = Field(default_factory=list, max_length=366)

    @field_validator("closed_weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("星期值必須介於 0 到 6。")
        return sorted(set(value))


class WorkCalendarResponse(WorkCalendarPayload):
    cutoff_time: str = "13:00"
    timezone: str = "Asia/Taipei"


def _calendar_response(setting: WorkCalendarSetting | None) -> WorkCalendarResponse:
    return WorkCalendarResponse(
        closed_weekdays=(
            setting.closed_weekdays_json if setting else list(DEFAULT_CLOSED_WEEKDAYS)
        ),
        holiday_dates=(
            [date.fromisoformat(value) for value in setting.holiday_dates_json]
            if setting
            else []
        ),
        working_dates=(
            [date.fromisoformat(value) for value in setting.working_dates_json]
            if setting
            else []
        ),
    )


@router.get("/work-calendar")
def get_work_calendar(
    _: OpsAccess,
    session: SessionDependency,
) -> WorkCalendarResponse:
    return _calendar_response(session.get(WorkCalendarSetting, "singleton"))


@router.patch("/work-calendar")
def update_work_calendar(
    payload: WorkCalendarPayload,
    _: OpsAccess,
    session: SessionDependency,
) -> WorkCalendarResponse:
    if len(payload.closed_weekdays) == 7:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "NO_WEEKLY_WORKDAY",
                "message": "每週至少要保留一個工作日。",
            },
        )
    overlap = set(payload.holiday_dates) & set(payload.working_dates)
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "CALENDAR_DATE_CONFLICT",
                "message": "同一日期不能同時設定為休假日與補班日。",
            },
        )
    setting = session.get(WorkCalendarSetting, "singleton")
    values = {
        "closed_weekdays_json": payload.closed_weekdays,
        "holiday_dates_json": sorted(day.isoformat() for day in set(payload.holiday_dates)),
        "working_dates_json": sorted(day.isoformat() for day in set(payload.working_dates)),
    }
    if setting is None:
        setting = WorkCalendarSetting(id="singleton", **values)
        session.add(setting)
    else:
        for field, value in values.items():
            setattr(setting, field, value)
    session.commit()
    return _calendar_response(setting)
