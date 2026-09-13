from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.access import OpsAccess
from app.core.config import get_settings
from app.dependencies import SessionDependency
from app.models import Message, Platform, RawEvent, SourceConnection, SourceSyncState

router = APIRouter(prefix="/api", tags=["source-health"])

# 需要管理者留意的狀態（會讓整體收訊亮「需注意」總燈）。
# Gmail 為選用來源，未連結／等待首次同步屬正常，不列入需注意。
_LINE_ATTENTION = {"ERROR", "STALE", "NO_DATA"}
_GMAIL_ATTENTION = {"ERROR", "STALE"}


class SourceHealth(BaseModel):
    platform: str
    status: str
    last_received_at: datetime | None
    hours_since_last_received: float | None
    messages_last_24h: int
    failures_last_24h: int
    detail: str


class SourceHealthResponse(BaseModel):
    generated_at: datetime
    overall_status: str
    attention: list[str]
    sources: list[SourceHealth]


@router.get("/sources/health")
def source_health(_: OpsAccess, session: SessionDependency) -> SourceHealthResponse:
    now = datetime.now(UTC)
    since = now - timedelta(hours=24)
    sources = [_line_health(session, since, now), _gmail_health(session, since, now)]
    attention = [
        _label(source.platform)
        for source in sources
        if _needs_attention(source)
    ]
    return SourceHealthResponse(
        generated_at=now,
        overall_status="ATTENTION" if attention else "HEALTHY",
        attention=attention,
        sources=sources,
    )


def _line_health(session, since: datetime, now: datetime) -> SourceHealth:  # type: ignore[no-untyped-def]
    stale_hours = get_settings().line_stale_hours
    count = session.scalar(
        select(func.count(Message.id)).where(
            Message.platform == Platform.LINE.value,
            Message.received_at >= since,
        )
    ) or 0
    last_received = session.scalar(
        select(func.max(Message.received_at)).where(Message.platform == Platform.LINE.value)
    )
    hours_since = _hours_since(now, last_received)
    failures = _failure_count(session, Platform.LINE.value, since)
    if failures:
        status = "ERROR"
        detail = f"近 24 小時有 {failures} 筆訊息處理失敗，請檢查"
    elif last_received is None:
        status, detail = "NO_DATA", "尚未收到任何 LINE 訊息"
    elif hours_since is not None and hours_since > stale_hours:
        status = "STALE"
        detail = (
            f"距上次收到已約 {hours_since:.0f} 小時"
            f"（超過 {stale_hours} 小時門檻），請確認 LINE 是否斷線"
        )
    else:
        status, detail = "HEALTHY", f"近 24 小時收到 {count} 則訊息"
    return SourceHealth(
        platform=Platform.LINE.value,
        status=status,
        last_received_at=last_received,
        hours_since_last_received=hours_since,
        messages_last_24h=count,
        failures_last_24h=failures,
        detail=detail,
    )


def _gmail_health(session, since: datetime, now: datetime) -> SourceHealth:  # type: ignore[no-untyped-def]
    count = session.scalar(
        select(func.count(Message.id)).where(
            Message.platform == Platform.GMAIL.value,
            Message.received_at >= since,
        )
    ) or 0
    last_received = session.scalar(
        select(func.max(Message.received_at)).where(Message.platform == Platform.GMAIL.value)
    )
    connection = session.scalar(
        select(SourceConnection)
        .where(SourceConnection.platform == Platform.GMAIL.value)
        .order_by(SourceConnection.updated_at.desc())
        .limit(1)
    )
    sync = (
        session.scalar(
            select(SourceSyncState).where(SourceSyncState.connection_id == connection.id)
        )
        if connection is not None
        else None
    )
    failures = _failure_count(session, Platform.GMAIL.value, since)
    if connection is None:
        status, detail = "NOT_CONNECTED", "尚未連結 Gmail"
    elif connection.status == "ERROR" or (sync is not None and sync.last_error):
        status, detail = "ERROR", "Gmail 最近一次同步失敗"
    elif sync is None or sync.last_sync_at is None:
        status, detail = "PENDING", "等待第一次 Gmail 同步"
    elif now - _as_utc(sync.last_sync_at) > timedelta(hours=2):
        status, detail = "STALE", "Gmail 超過 2 小時未同步"
    else:
        status, detail = "HEALTHY", "Gmail 同步正常"
    return SourceHealth(
        platform=Platform.GMAIL.value,
        status=status,
        last_received_at=last_received,
        hours_since_last_received=_hours_since(now, last_received),
        messages_last_24h=count,
        failures_last_24h=failures,
        detail=detail,
    )


def _needs_attention(source: SourceHealth) -> bool:
    if source.platform == Platform.LINE.value:
        return source.status in _LINE_ATTENTION
    if source.platform == Platform.GMAIL.value:
        return source.status in _GMAIL_ATTENTION
    return source.status in _LINE_ATTENTION


def _label(platform: str) -> str:
    return "Gmail" if platform == Platform.GMAIL.value else "LINE"


def _failure_count(session, platform: str, since: datetime) -> int:  # type: ignore[no-untyped-def]
    return session.scalar(
        select(func.count(RawEvent.id)).where(
            RawEvent.platform == platform,
            RawEvent.received_at >= since,
            RawEvent.processing_status.in_(["FAILED_RETRYABLE", "FAILED_PERMANENT"]),
        )
    ) or 0


def _hours_since(now: datetime, value: datetime | None) -> float | None:
    if value is None:
        return None
    delta = now - _as_utc(value)
    return round(max(delta.total_seconds(), 0.0) / 3600, 1)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
