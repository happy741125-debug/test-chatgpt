from __future__ import annotations

import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import JobQueueDependency, SessionDependency
from app.gmail.crypto import CredentialCipher
from app.gmail.oauth import (
    GMAIL_READONLY_SCOPE,
    GmailAPIClient,
    GmailAPIError,
    GmailOAuthClient,
    build_authorization_url,
)
from app.gmail.sync import GmailSyncResult, sync_gmail_connection
from app.models import (
    Platform,
    SourceConnection,
    SourceConnectionStatus,
    SourceOAuthState,
    SourceSyncState,
)

router = APIRouter(prefix="/api/gmail", tags=["gmail"])
logger = logging.getLogger(__name__)


class GmailConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str | None
    status: str
    connected_at: datetime | None
    last_sync_at: datetime | None
    initial_sync_completed: bool
    last_error: str | None


class GmailConnectResponse(BaseModel):
    authorization_url: str


class GmailSyncResponse(BaseModel):
    connection_id: str
    examined: int
    created: int
    duplicate: int
    unsupported: int
    jobs_published: int
    mode: str


class GmailAutoSyncResponse(BaseModel):
    examined_connections: int
    synced_connections: int
    failed_connections: int
    messages_created: int
    duplicate_messages: int
    jobs_published: int


@router.get("/connections")
def list_connections(
    _: OpsAccess,
    session: SessionDependency,
) -> list[GmailConnectionResponse]:
    connections = session.scalars(
        select(SourceConnection)
        .where(SourceConnection.platform == Platform.GMAIL.value)
        .order_by(SourceConnection.created_at.desc())
    ).all()
    return [_connection_response(session, connection) for connection in connections]


@router.post("/connect")
def start_connection(
    _: OpsAccess,
    request: Request,
    session: SessionDependency,
) -> GmailConnectResponse:
    settings = request.app.state.settings
    if not settings.gmail_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "GMAIL_NOT_CONFIGURED",
                "message": "Gmail 尚未完成 Google 連線設定。",
            },
        )
    state_value = secrets.token_urlsafe(48)
    session.add(
        SourceOAuthState(
            state=state_value,
            platform=Platform.GMAIL.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    session.commit()
    return GmailConnectResponse(
        authorization_url=build_authorization_url(
            client_id=settings.gmail_client_id,
            redirect_uri=settings.gmail_redirect_uri,
            state=state_value,
        )
    )


@router.get("/callback")
def gmail_callback(
    request: Request,
    session: SessionDependency,
    state: str | None = Query(default=None),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    settings = request.app.state.settings
    if error or not state or not code:
        return _dashboard_redirect(settings.dashboard_url, "error", "authorization_cancelled")

    oauth_state = session.get(SourceOAuthState, state)
    now = datetime.now(UTC)
    if (
        oauth_state is None
        or oauth_state.platform != Platform.GMAIL.value
        or oauth_state.consumed_at is not None
        or _as_utc(oauth_state.expires_at) < now
    ):
        return _dashboard_redirect(settings.dashboard_url, "error", "authorization_expired")
    oauth_state.consumed_at = now
    session.commit()

    try:
        oauth = GmailOAuthClient(
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret,
            redirect_uri=settings.gmail_redirect_uri,
        )
        tokens = oauth.exchange_code(code)
        profile = GmailAPIClient(tokens.access_token).get_profile()
        connection = session.scalar(
            select(SourceConnection).where(
                SourceConnection.platform == Platform.GMAIL.value,
                SourceConnection.external_account_id == profile.email_address,
            )
        )
        if connection is None:
            connection = SourceConnection(
                platform=Platform.GMAIL.value,
                external_account_id=profile.email_address,
                status=SourceConnectionStatus.PENDING.value,
            )
            session.add(connection)
            session.flush()
        if tokens.refresh_token:
            connection.encrypted_refresh_token = CredentialCipher(
                settings.credential_encryption_secret
            ).encrypt(tokens.refresh_token)
        if not connection.encrypted_refresh_token:
            raise GmailAPIError("Google did not return reusable mailbox authorization")
        connection.scopes_json = tokens.scope.split() or [GMAIL_READONLY_SCOPE]
        connection.status = SourceConnectionStatus.ACTIVE.value
        connection.connected_at = now
        connection.last_error = None
        sync_state = session.scalar(
            select(SourceSyncState).where(SourceSyncState.connection_id == connection.id)
        )
        if sync_state is None:
            session.add(SourceSyncState(connection_id=connection.id, history_id=profile.history_id))
        session.commit()
    except Exception:
        session.rollback()
        return _dashboard_redirect(
            settings.dashboard_url,
            "error",
            "google_connection_failed",
        )
    return _dashboard_redirect(settings.dashboard_url, "connected")


@router.post("/connections/{connection_id}/sync")
def sync_connection(
    connection_id: str,
    _: OpsAccess,
    request: Request,
    session: SessionDependency,
    queue: JobQueueDependency,
) -> GmailSyncResponse:
    if not request.app.state.settings.gmail_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "GMAIL_NOT_CONFIGURED"},
        )
    try:
        result: GmailSyncResult = sync_gmail_connection(
            session,
            queue,
            request.app.state.settings,
            connection_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "GMAIL_CONNECTION_NOT_FOUND"},
        ) from exc
    except GmailAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_code": "GMAIL_SYNC_FAILED"},
        ) from exc
    return GmailSyncResponse(**result.__dict__)


@router.post("/auto-sync")
def auto_sync_connections(
    request: Request,
    session: SessionDependency,
    queue: JobQueueDependency,
    sync_token: str | None = Header(default=None, alias="X-Gmail-Sync-Token"),
) -> GmailAutoSyncResponse:
    settings = request.app.state.settings
    if not settings.gmail_sync_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "GMAIL_AUTO_SYNC_NOT_CONFIGURED"},
        )
    if not sync_token or not hmac.compare_digest(sync_token, settings.gmail_sync_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "GMAIL_AUTO_SYNC_ACCESS_DENIED"},
        )
    if not settings.gmail_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "GMAIL_NOT_CONFIGURED"},
        )

    connections = session.scalars(
        select(SourceConnection)
        .where(
            SourceConnection.platform == Platform.GMAIL.value,
            SourceConnection.status.in_(
                [SourceConnectionStatus.ACTIVE.value, SourceConnectionStatus.ERROR.value]
            ),
            SourceConnection.encrypted_refresh_token.is_not(None),
        )
        .order_by(SourceConnection.created_at)
    ).all()

    synced = 0
    failed = 0
    created = 0
    duplicate = 0
    published = 0
    for connection in connections:
        try:
            result = sync_gmail_connection(session, queue, settings, connection.id)
        except Exception:  # noqa: BLE001 - one mailbox must not block the others
            failed += 1
            logger.exception(
                "Automatic Gmail sync failed",
                extra={"connection_id": connection.id},
            )
            continue
        synced += 1
        created += result.created
        duplicate += result.duplicate
        published += result.jobs_published

    return GmailAutoSyncResponse(
        examined_connections=len(connections),
        synced_connections=synced,
        failed_connections=failed,
        messages_created=created,
        duplicate_messages=duplicate,
        jobs_published=published,
    )


def _connection_response(session, connection: SourceConnection) -> GmailConnectionResponse:  # type: ignore[no-untyped-def]
    sync_state = session.scalar(
        select(SourceSyncState).where(SourceSyncState.connection_id == connection.id)
    )
    return GmailConnectionResponse(
        id=connection.id,
        email=connection.external_account_id,
        display_name=connection.display_name,
        status=connection.status,
        connected_at=connection.connected_at,
        last_sync_at=sync_state.last_sync_at if sync_state else None,
        initial_sync_completed=bool(sync_state and sync_state.initial_sync_completed),
        last_error=connection.last_error or (sync_state.last_error if sync_state else None),
    )


def _dashboard_redirect(base_url: str, result: str, reason: str | None = None) -> RedirectResponse:
    params = {"gmail": result}
    if reason:
        params["reason"] = reason
    return RedirectResponse(f"{base_url.rstrip('/')}?{urlencode(params)}", status_code=303)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
