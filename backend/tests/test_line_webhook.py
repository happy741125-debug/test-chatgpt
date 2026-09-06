from __future__ import annotations

import json

from sqlalchemy import func, select

from app.line.security import make_signature
from app.models import Channel, Conversation, Identity, Message, ProcessingJob, RawEvent

SECRET = "test-channel-secret"


def line_payload() -> dict[str, object]:
    return {
        "destination": "Udestination",
        "events": [
            {
                "type": "message",
                "mode": "active",
                "timestamp": 1788686400000,
                "source": {
                    "type": "group",
                    "groupId": "Cgroup001",
                    "userId": "Ukevin001",
                },
                "webhookEventId": "01H-WEBHOOK-001",
                "deliveryContext": {"isRedelivery": False},
                "message": {
                    "id": "5950000000001",
                    "type": "text",
                    "quoteToken": "test-quote-token",
                    "text": "A 客戶的貨差 20 箱，Kevin 已經向廠商叫貨。",
                },
            }
        ],
    }


def signed_request(client, payload: dict[str, object]):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = make_signature(body, SECRET)
    return client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )


def count(database, model) -> int:
    with database.session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_valid_message_is_saved_before_queueing(test_context) -> None:
    client, database, queue = test_context

    response = signed_request(client, line_payload())

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "events_accepted": 1,
        "events_duplicate": 0,
        "messages_created": 1,
        "unsupported_events": 0,
        "jobs_published": 1,
    }
    assert count(database, RawEvent) == 1
    assert count(database, Message) == 1
    assert count(database, Channel) == 1
    assert count(database, Conversation) == 1
    assert count(database, Identity) == 1
    assert count(database, ProcessingJob) == 1
    assert len(queue.ready) == 1

    with database.session_factory() as session:
        channel = session.scalar(select(Channel))
        message = session.scalar(select(Message))
        assert channel is not None and channel.silent_mode is True
        assert message is not None and message.text == "A 客戶的貨差 20 箱，Kevin 已經向廠商叫貨。"


def test_redelivery_is_idempotent(test_context) -> None:
    client, database, queue = test_context

    first = signed_request(client, line_payload())
    second = signed_request(client, line_payload())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["events_duplicate"] == 1
    assert second.json()["messages_created"] == 0
    assert second.json()["jobs_published"] == 0
    assert count(database, RawEvent) == 1
    assert count(database, Message) == 1
    assert count(database, ProcessingJob) == 1
    assert len(queue.ready) == 1


def test_invalid_signature_is_rejected_without_writes(test_context) -> None:
    client, database, queue = test_context
    body = json.dumps(line_payload()).encode("utf-8")

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={"Content-Type": "application/json", "X-Line-Signature": "invalid"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "INVALID_LINE_SIGNATURE"
    assert count(database, RawEvent) == 0
    assert count(database, Message) == 0
    assert queue.ready == []


def test_unsupported_event_is_retained_without_message(test_context) -> None:
    client, database, queue = test_context
    payload = {
        "events": [
            {
                "type": "follow",
                "timestamp": 1788686400000,
                "source": {"type": "user", "userId": "Unew"},
                "webhookEventId": "01H-FOLLOW-001",
            }
        ]
    }

    response = signed_request(client, payload)

    assert response.status_code == 200
    assert response.json()["events_accepted"] == 1
    assert response.json()["unsupported_events"] == 1
    assert count(database, RawEvent) == 1
    assert count(database, Message) == 0
    assert queue.ready == []


class FailingQueue:
    def publish(self, job_id: str) -> None:
        raise ConnectionError(f"queue unavailable for {job_id}")

    def ping(self) -> bool:
        return False


def test_queue_outage_does_not_lose_durable_message() -> None:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.db import Database
    from app.main import create_app

    settings = Settings(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        line_channel_secret=SECRET,
        line_silent_mode=True,
        auto_create_schema=True,
    )
    database = Database(settings.database_url)
    app = create_app(settings=settings, database=database, queue=FailingQueue())

    with TestClient(app) as client:
        response = signed_request(client, line_payload())

    assert response.status_code == 200
    assert response.json()["messages_created"] == 1
    assert response.json()["jobs_published"] == 0
    assert count(database, Message) == 1
    assert count(database, ProcessingJob) == 1
    database.engine.dispose()
