from __future__ import annotations

import json

from sqlalchemy import func, select

from app.line.security import make_signature
from app.models import Channel, Message, ProcessingJob, RawEvent

SECRET = "test-channel-secret"


def _payload(event_id: str, message_id: str, text: str) -> dict[str, object]:
    return {
        "events": [
            {
                "type": "message",
                "timestamp": 1788686400000,
                "source": {"type": "group", "groupId": "C-settings", "userId": "U-user"},
                "webhookEventId": event_id,
                "message": {"id": message_id, "type": "text", "text": text},
            }
        ]
    }


def _post(client, payload: dict[str, object]):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": make_signature(body, SECRET),
        },
    )


def _count(database, model) -> int:
    with database.session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_channel_can_be_listed_and_updated(test_context) -> None:
    client, _, _ = test_context
    _post(client, _payload("event-settings-1", "message-settings-1", "第一則訊息"))

    listed = client.get("/api/channels")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    channel_id = listed.json()[0]["id"]
    assert listed.json()[0]["monitoring_level"] == "B"
    assert listed.json()[0]["silent_mode"] is True

    updated = client.patch(
        f"/api/channels/{channel_id}",
        json={"name": "貨達測試群", "monitoring_level": "C", "enabled": True},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "貨達測試群"
    assert updated.json()["monitoring_level"] == "C"
    assert updated.json()["silent_mode"] is True

    detail = client.get(f"/api/channels/{channel_id}")
    assert detail.status_code == 200
    assert detail.json() == updated.json()


def test_invalid_monitoring_level_is_rejected(test_context) -> None:
    client, _, _ = test_context
    _post(client, _payload("event-settings-2", "message-settings-2", "建立群組"))
    channel_id = client.get("/api/channels").json()[0]["id"]

    response = client.patch(
        f"/api/channels/{channel_id}",
        json={"monitoring_level": "Z"},
    )

    assert response.status_code == 422


def test_level_d_retains_message_but_skips_processing_job(test_context) -> None:
    client, database, queue = test_context
    _post(client, _payload("event-settings-3", "message-settings-3", "第一則訊息"))
    with database.session_factory() as session:
        channel = session.scalar(select(Channel))
        assert channel is not None
        channel_id = channel.id

    response = client.patch(
        f"/api/channels/{channel_id}",
        json={"monitoring_level": "D"},
    )
    assert response.status_code == 200

    second = _post(client, _payload("event-settings-4", "message-settings-4", "不分析這則"))

    assert second.status_code == 200
    assert second.json()["messages_created"] == 1
    assert second.json()["jobs_published"] == 0
    assert _count(database, RawEvent) == 2
    assert _count(database, Message) == 2
    assert _count(database, ProcessingJob) == 1
    assert len(queue.ready) == 1


def test_missing_channel_returns_not_found(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/api/channels/missing")

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "CHANNEL_NOT_FOUND"
