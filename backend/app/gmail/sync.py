from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.gmail.crypto import CredentialCipher
from app.gmail.oauth import GmailAPIClient, GmailAPIError, GmailOAuthClient
from app.models import SourceConnection, SourceConnectionStatus, SourceSyncState
from app.queue import JobQueue
from app.services.gmail_ingestion import ingest_gmail_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GmailSyncResult:
    connection_id: str
    examined: int
    created: int
    duplicate: int
    unsupported: int
    jobs_published: int
    mode: str


def sync_gmail_connection(
    session: Session,
    queue: JobQueue,
    settings: Settings,
    connection_id: str,
) -> GmailSyncResult:
    connection = session.get(SourceConnection, connection_id)
    if connection is None or connection.status == SourceConnectionStatus.DISCONNECTED.value:
        raise ValueError("Gmail connection does not exist")
    if not connection.encrypted_refresh_token:
        raise ValueError("Gmail connection has no stored authorization")

    sync_state = session.scalar(
        select(SourceSyncState).where(SourceSyncState.connection_id == connection.id)
    )
    if sync_state is None:
        sync_state = SourceSyncState(connection_id=connection.id)
        session.add(sync_state)
        session.flush()

    oauth = GmailOAuthClient(
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        redirect_uri=settings.gmail_redirect_uri,
    )
    cipher = CredentialCipher(settings.credential_encryption_secret)
    try:
        refresh_token = cipher.decrypt(connection.encrypted_refresh_token)
        access_token = oauth.refresh_access_token(refresh_token)
        api = GmailAPIClient(access_token)
        profile = api.get_profile()
        mode = (
            "incremental"
            if sync_state.initial_sync_completed and sync_state.history_id
            else "initial"
        )
        if mode == "incremental":
            try:
                message_ids = api.list_history_message_ids(
                    start_history_id=sync_state.history_id or "",
                    limit=settings.gmail_initial_sync_limit,
                )
            except GmailAPIError as exc:
                if exc.status_code != 404:
                    raise
                mode = "recovery"
                message_ids = api.list_recent_message_ids(
                    days=settings.gmail_initial_sync_days,
                    limit=settings.gmail_initial_sync_limit,
                )
        else:
            message_ids = api.list_recent_message_ids(
                days=settings.gmail_initial_sync_days,
                limit=settings.gmail_initial_sync_limit,
            )

        created = 0
        duplicate = 0
        unsupported = 0
        jobs_published = 0
        latest_message_at = sync_state.last_message_at
        payloads = _fetch_available_messages(api, message_ids)
        payloads.sort(key=_internal_date)
        for payload in payloads:
            result = ingest_gmail_message(
                session,
                profile.email_address,
                payload,
                retention_days=settings.raw_event_retention_days,
                attachment_retention_days=settings.attachment_retention_days,
                attachment_max_bytes=settings.attachment_max_bytes,
            )
            created += int(result.created)
            duplicate += int(result.duplicate)
            unsupported += int(result.unsupported)
            if result.created:
                internal_date = payload.get("internalDate")
                try:
                    message_at = datetime.fromtimestamp(int(str(internal_date)) / 1000, tz=UTC)
                except (TypeError, ValueError, OSError):
                    message_at = None
                if message_at and (
                    latest_message_at is None or message_at > _as_utc(latest_message_at)
                ):
                    latest_message_at = message_at
            for job_id in result.job_ids:
                queue.publish(job_id)
                jobs_published += 1

        now = datetime.now(UTC)
        sync_state.history_id = profile.history_id
        sync_state.initial_sync_completed = True
        sync_state.last_sync_at = now
        sync_state.last_message_at = latest_message_at
        sync_state.last_error = None
        connection.status = SourceConnectionStatus.ACTIVE.value
        connection.last_error = None
        session.commit()
        return GmailSyncResult(
            connection_id=connection.id,
            examined=len(message_ids),
            created=created,
            duplicate=duplicate,
            unsupported=unsupported,
            jobs_published=jobs_published,
            mode=mode,
        )
    except Exception as exc:
        connection.status = SourceConnectionStatus.ERROR.value
        connection.last_error = str(exc)[:1000]
        sync_state.last_error = str(exc)[:1000]
        session.commit()
        raise


def _internal_date(payload: dict[str, object]) -> int:
    try:
        return int(str(payload.get("internalDate")))
    except (TypeError, ValueError):
        return 0


def _fetch_available_messages(
    api: GmailAPIClient,
    message_ids: list[str],
) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for message_id in message_ids:
        try:
            payloads.append(api.get_message(message_id))
        except GmailAPIError as exc:
            if exc.status_code != 404:
                raise
            logger.warning(
                "Skipping Gmail message that disappeared before it could be fetched",
                extra={"gmail_message_id": message_id},
            )
    return payloads


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
