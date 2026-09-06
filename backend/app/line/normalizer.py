from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class NormalizedLineMessage:
    external_message_id: str
    external_channel_id: str
    channel_type: str
    external_conversation_id: str
    sender_external_id: str | None
    message_type: str
    text: str | None
    source_created_at: datetime
    metadata: dict[str, Any]


def normalize_line_message(event: dict[str, Any]) -> NormalizedLineMessage | None:
    if event.get("type") != "message":
        return None

    message = event.get("message")
    source = event.get("source")
    if not isinstance(message, dict) or not isinstance(source, dict):
        return None

    message_id = message.get("id")
    source_type = source.get("type")
    channel_id = _channel_id(source)
    if not isinstance(message_id, str) or not message_id or channel_id is None:
        return None

    timestamp = event.get("timestamp")
    created_at = _timestamp_to_datetime(timestamp)
    message_type = str(message.get("type") or "unknown")
    text = message.get("text") if message_type == "text" else None
    if text is not None and not isinstance(text, str):
        text = str(text)

    metadata = {
        key: value
        for key, value in message.items()
        if key not in {"id", "text"}
    }

    return NormalizedLineMessage(
        external_message_id=message_id,
        external_channel_id=channel_id,
        channel_type=str(source_type or "unknown"),
        external_conversation_id=channel_id,
        sender_external_id=_string_or_none(source.get("userId")),
        message_type=message_type,
        text=text,
        source_created_at=created_at,
        metadata=metadata,
    )


def _channel_id(source: dict[str, Any]) -> str | None:
    source_type = source.get("type")
    if source_type == "group":
        return _string_or_none(source.get("groupId"))
    if source_type == "room":
        return _string_or_none(source.get("roomId"))
    if source_type == "user":
        return _string_or_none(source.get("userId"))
    return None


def _timestamp_to_datetime(value: Any) -> datetime:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    return datetime.now(UTC)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
