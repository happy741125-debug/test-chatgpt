from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import Message, Platform, RawEvent, SourceConnection, SourceSyncState

router = APIRouter(prefix="/api", tags=["source-health"])


class SourceHealth(BaseModel):
    platform: str
    status: str
    last_received_at: datetime | None
    messages_last_24h: int
    failures_last_24h: int
    detail: str


class SourceHealthResponse(BaseModel):
    generated_at: datetime
    sources: list[SourceHealth]


@router.get("/sources/health")
def source_health(_: OpsAccess, session: SessionDependency) -> SourceHealthResponse:
    now = datetime.now(UTC)
    since = now - timedelta(hours=24)
    sources = [_line_health(session, since), _gmail_health(session, since, now)]
    return SourceHealthResponse(generated_at=now, sources=sources)


def _line_health(session, since: datetime) -> SourceHealth:  # type: ignore[no-untyped-def]
    count = session.scalar(
        select(func.count(Message.id)).where(
            Message.platform == Platform.LINE.value,
            Message.received_at >= since,
        )
    ) or 0
    last_received = session.scalar(
        select(func.max(Message.received_at)).where(Message.platform == Platform.LINE.value)
    )
    failures = _failure_count(session, Platform.LINE.value, since)
    status = "ERROR" if failures else ("HEALTHY" if count else "NO_RECENT_DATA")
    detail = "近 24 小時持續收到訊息" if count else "近 24 小時尚未收到 LINE 訊息"
    return SourceHealth(
        platform=Platform.LINE.value,
        status=status,
        last_received_at=last_received,
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
        messages_last_24h=count,
        failures_last_24h=failures,
        detail=detail,
    )


def _failure_count(session, platform: str, since: datetime) -> int:  # type: ignore[no-untyped-def]
    return session.scalar(
        select(func.count(RawEvent.id)).where(
            RawEvent.platform == platform,
            RawEvent.received_at >= since,
            RawEvent.processing_status.in_(["FAILED_RETRYABLE", "FAILED_PERMANENT"]),
        )
    ) or 0


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
