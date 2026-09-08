from __future__ import annotations

import base64
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db import Database
from app.gmail.normalizer import normalize_gmail_message
from app.gmail.oauth import GmailAPIError
from app.gmail.sync import GmailSyncResult, _fetch_available_messages
from app.main import create_app
from app.models import (
    Channel,
    Conversation,
    Identity,
    Message,
    Platform,
    ProcessingJob,
    RawEvent,
    SourceConnection,
    SourceConnectionStatus,
    SourceOAuthState,
)
from app.queue import InMemoryJobQueue
from app.services.context import ContextBuilder
from app.services.gmail_ingestion import ingest_gmail_message

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


class _MessageAPIStub:
    def __init__(self, responses: dict[str, dict[str, object] | Exception]) -> None:
        self.responses = responses

    def get_message(self, message_id: str) -> dict[str, object]:
        response = self.responses[message_id]
        if isinstance(response, Exception):
            raise response
        return response


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _gmail_payload(
    *,
    message_id: str = "gmail-message-1",
    thread_id: str = "gmail-thread-1",
    internal_date: str = "4102444800000",
) -> dict[str, object]:
    return {
        "id": message_id,
        "threadId": thread_id,
        "internalDate": internal_date,
        "labelIds": ["INBOX"],
        "snippet": "測試摘要",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "測試客戶 <customer@example.com>"},
                {"name": "To", "value": "ops@example.com"},
                {"name": "Subject", "value": "明天安排出貨"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": _encoded("新增一筆急單，明天務必出貨。\n--\n測試簽名")},
                }
            ],
        },
    }


def test_normalize_gmail_message_extracts_safe_thread_text() -> None:
    normalized = normalize_gmail_message("OPS@EXAMPLE.COM", _gmail_payload())

    assert normalized is not None
    assert normalized.account_email == "ops@example.com"
    assert normalized.external_thread_id == "gmail-thread-1"
    assert normalized.sender_email == "customer@example.com"
    assert normalized.subject == "明天安排出貨"
    assert normalized.text == "主旨：明天安排出貨\n新增一筆急單，明天務必出貨。"
    assert "測試簽名" not in normalized.text
    assert normalized.metadata["message_category"] == "PRIMARY"
    assert normalized.metadata["work_relevant"] is True


def test_newsletter_is_saved_but_not_queued_for_intelligence(test_context) -> None:
    _, database, _ = test_context
    payload = _gmail_payload(message_id="newsletter-message")
    payload["labelIds"] = ["INBOX", "CATEGORY_PROMOTIONS"]
    message_payload = payload["payload"]
    assert isinstance(message_payload, dict)
    headers = message_payload["headers"]
    assert isinstance(headers, list)
    headers.append({"name": "List-Unsubscribe", "value": "<mailto:unsubscribe@example.com>"})
    for header in headers:
        if isinstance(header, dict) and header.get("name") == "Subject":
            header["value"] = "九月優惠電子報"
    parts = message_payload["parts"]
    assert isinstance(parts, list)
    parts[0]["body"] = {"data": _encoded("本月活動快訊，立即購買享折扣。")}

    with database.session_factory() as session:
        result = ingest_gmail_message(session, "ops@example.com", payload)

    assert result.created is True
    assert result.job_ids == []
    with database.session_factory() as session:
        message = session.scalar(select(Message))
        assert message is not None
        assert message.metadata_json["message_category"] == "NEWSLETTER"
        assert message.metadata_json["work_relevant"] is False
        assert session.scalar(select(func.count()).select_from(ProcessingJob)) == 0


def test_missing_history_message_does_not_abort_gmail_sync() -> None:
    expected = _gmail_payload(message_id="available-message")
    api = _MessageAPIStub(
        {
            "disappeared-message": GmailAPIError("not found", status_code=404),
            "available-message": expected,
        }
    )

    payloads = _fetch_available_messages(  # type: ignore[arg-type]
        api,
        ["disappeared-message", "available-message"],
    )

    assert payloads == [expected]


def test_non_missing_gmail_error_still_aborts_sync() -> None:
    api = _MessageAPIStub({"failed-message": GmailAPIError("unavailable", status_code=503)})

    with pytest.raises(GmailAPIError):
        _fetch_available_messages(api, ["failed-message"])  # type: ignore[arg-type]


def test_gmail_ingestion_is_idempotent_and_queues_context(test_context) -> None:
    _, database, queue = test_context
    payload = _gmail_payload()
    with database.session_factory() as session:
        first = ingest_gmail_message(session, "ops@example.com", payload)
        second = ingest_gmail_message(session, "ops@example.com", payload)

    assert first.created is True
    assert len(first.job_ids) == 1
    assert second.duplicate is True
    queue.publish(first.job_ids[0])
    assert len(queue.ready) == 1

    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RawEvent)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 1
        assert session.scalar(select(func.count()).select_from(Channel)) == 1
        assert session.scalar(select(func.count()).select_from(Conversation)) == 1
        assert session.scalar(select(func.count()).select_from(Identity)) == 1
        assert session.scalar(select(func.count()).select_from(ProcessingJob)) == 1
        message = session.scalar(select(Message))
        assert message is not None
        assert message.platform == Platform.GMAIL.value
        assert message.metadata_json["subject"] == "明天安排出貨"


def test_gmail_thread_messages_share_context_across_multiple_days(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        first = ingest_gmail_message(
            session,
            "ops@example.com",
            _gmail_payload(message_id="gmail-old", internal_date="4102444800000"),
        )
        second = ingest_gmail_message(
            session,
            "ops@example.com",
            _gmail_payload(message_id="gmail-new", internal_date="4102617600000"),
        )

    assert first.message_id is not None and second.message_id is not None
    builder = ContextBuilder(database.session_factory, window_minutes=15, max_messages=30)
    first_context = builder.add_message(first.message_id)
    second_context = builder.add_message(second.message_id)

    assert second_context.context_id == first_context.context_id


def test_gmail_connect_requires_server_configuration(test_context) -> None:
    client, _, _ = test_context

    response = client.post("/api/gmail/connect", headers=OPS_HEADERS)

    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "GMAIL_NOT_CONFIGURED"


def test_gmail_connect_creates_short_lived_state_and_read_only_url() -> None:
    settings = Settings(
        app_env="test",
        ops_api_token="test-ops-token",
        database_url="sqlite+pysqlite:///:memory:",
        line_channel_secret="test-channel-secret",
        gmail_client_id="test-client.apps.googleusercontent.com",
        gmail_client_secret="test-client-secret",
        gmail_redirect_uri="https://api.example.com/api/gmail/callback",
        credential_encryption_secret="test-encryption-secret",
        auto_create_schema=True,
        _env_file=None,
    )
    database = Database(settings.database_url)
    app = create_app(settings=settings, database=database, queue=InMemoryJobQueue())
    try:
        with TestClient(app) as client:
            response = client.post("/api/gmail/connect", headers=OPS_HEADERS)
        assert response.status_code == 200
        authorization_url = response.json()["authorization_url"]
        query = parse_qs(urlparse(authorization_url).query)
        assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
        assert query["access_type"] == ["offline"]
        assert query["redirect_uri"] == ["https://api.example.com/api/gmail/callback"]
        assert "test-client-secret" not in authorization_url
        with database.session_factory() as session:
            oauth_state = session.scalar(select(SourceOAuthState))
            assert oauth_state is not None
            assert oauth_state.consumed_at is None
            assert oauth_state.expires_at > datetime.now(UTC).replace(tzinfo=None)
    finally:
        database.engine.dispose()


def test_gmail_auto_sync_requires_scheduler_token() -> None:
    settings = Settings(
        app_env="test",
        ops_api_token="test-ops-token",
        database_url="sqlite+pysqlite:///:memory:",
        line_channel_secret="test-channel-secret",
        gmail_client_id="test-client.apps.googleusercontent.com",
        gmail_client_secret="test-client-secret",
        gmail_redirect_uri="https://api.example.com/api/gmail/callback",
        credential_encryption_secret="test-encryption-secret",
        gmail_sync_token="test-sync-token",
        auto_create_schema=True,
        _env_file=None,
    )
    database = Database(settings.database_url)
    app = create_app(settings=settings, database=database, queue=InMemoryJobQueue())
    try:
        with TestClient(app) as client:
            response = client.post("/api/gmail/auto-sync")
        assert response.status_code == 403
        assert response.json()["detail"]["error_code"] == "GMAIL_AUTO_SYNC_ACCESS_DENIED"
    finally:
        database.engine.dispose()


def test_gmail_auto_sync_continues_when_one_mailbox_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        app_env="test",
        ops_api_token="test-ops-token",
        database_url="sqlite+pysqlite:///:memory:",
        line_channel_secret="test-channel-secret",
        gmail_client_id="test-client.apps.googleusercontent.com",
        gmail_client_secret="test-client-secret",
        gmail_redirect_uri="https://api.example.com/api/gmail/callback",
        credential_encryption_secret="test-encryption-secret",
        gmail_sync_token="test-sync-token",
        auto_create_schema=True,
        _env_file=None,
    )
    database = Database(settings.database_url)
    queue = InMemoryJobQueue()
    app = create_app(settings=settings, database=database, queue=queue)
    try:
        with TestClient(app) as client:
            with database.session_factory() as session:
                first = SourceConnection(
                    platform=Platform.GMAIL.value,
                    external_account_id="first@example.com",
                    status=SourceConnectionStatus.ACTIVE.value,
                    encrypted_refresh_token="encrypted-first",
                )
                second = SourceConnection(
                    platform=Platform.GMAIL.value,
                    external_account_id="second@example.com",
                    status=SourceConnectionStatus.ERROR.value,
                    encrypted_refresh_token="encrypted-second",
                )
                session.add_all([first, second])
                session.commit()
                successful_id = second.id

            def fake_sync(session, queue, settings, connection_id):  # type: ignore[no-untyped-def]
                if connection_id != successful_id:
                    raise GmailAPIError("temporary failure", status_code=503)
                return GmailSyncResult(
                    connection_id=connection_id,
                    examined=2,
                    created=1,
                    duplicate=1,
                    unsupported=0,
                    jobs_published=1,
                    mode="incremental",
                )

            monkeypatch.setattr("app.api.gmail.sync_gmail_connection", fake_sync)
            response = client.post(
                "/api/gmail/auto-sync",
                headers={"X-Gmail-Sync-Token": "test-sync-token"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "examined_connections": 2,
            "synced_connections": 1,
            "failed_connections": 1,
            "messages_created": 1,
            "duplicate_messages": 1,
            "jobs_published": 1,
        }
    finally:
        database.engine.dispose()
