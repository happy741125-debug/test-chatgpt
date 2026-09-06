from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.line.normalizer import NormalizedLineMessage, normalize_line_message
from app.models import (
    Channel,
    Conversation,
    Identity,
    Message,
    Platform,
    ProcessingJob,
    ProcessingStatus,
    RawEvent,
)


@dataclass
class IngestionResult:
    events_accepted: int = 0
    events_duplicate: int = 0
    messages_created: int = 0
    unsupported_events: int = 0
    job_ids: list[str] = field(default_factory=list)


def ingest_line_payload(
    session: Session,
    payload: dict[str, Any],
    *,
    silent_mode: bool,
) -> IngestionResult:
    result = IngestionResult()
    events = payload.get("events", [])
    if not isinstance(events, list):
        events = []

    for event in events:
        if not isinstance(event, dict):
            result.unsupported_events += 1
            continue

        external_event_id = _event_id(event)
        existing_event = session.scalar(
            select(RawEvent.id).where(
                RawEvent.platform == Platform.LINE.value,
                RawEvent.external_event_id == external_event_id,
            )
        )
        if existing_event is not None:
            result.events_duplicate += 1
            continue

        try:
            with session.begin_nested():
                raw_event = RawEvent(
                    platform=Platform.LINE.value,
                    external_event_id=external_event_id,
                    payload_json=event,
                    signature_valid=True,
                    processing_status=ProcessingStatus.RECEIVED.value,
                )
                session.add(raw_event)
                session.flush()
        except IntegrityError:
            # The database constraint is the final guard when redeliveries race.
            result.events_duplicate += 1
            continue
        result.events_accepted += 1

        normalized = normalize_line_message(event)
        if normalized is None:
            raw_event.processing_status = ProcessingStatus.UNSUPPORTED.value
            result.unsupported_events += 1
            continue

        message_exists = session.scalar(
            select(Message.id).where(
                Message.platform == Platform.LINE.value,
                Message.external_message_id == normalized.external_message_id,
            )
        )
        if message_exists is not None:
            raw_event.processing_status = ProcessingStatus.PROCESSED.value
            result.events_duplicate += 1
            continue

        message = _create_message(session, raw_event, normalized, silent_mode=silent_mode)
        channel = session.get(Channel, message.channel_id)
        if channel is not None and channel.enabled and channel.monitoring_level != "D":
            job = ProcessingJob(
                job_type="build_context",
                idempotency_key=f"build_context:{message.id}",
                payload_json={"message_id": message.id, "channel_id": message.channel_id},
            )
            session.add(job)
            session.flush()
            raw_event.processing_status = ProcessingStatus.QUEUED.value
            result.job_ids.append(job.id)
        else:
            message.processing_status = ProcessingStatus.PROCESSED.value
            raw_event.processing_status = ProcessingStatus.PROCESSED.value
        result.messages_created += 1

    session.commit()
    return result


def _create_message(
    session: Session,
    raw_event: RawEvent,
    normalized: NormalizedLineMessage,
    *,
    silent_mode: bool,
) -> Message:
    channel = session.scalar(
        select(Channel).where(
            Channel.platform == Platform.LINE.value,
            Channel.external_channel_id == normalized.external_channel_id,
        )
    )
    if channel is None:
        channel = Channel(
            platform=Platform.LINE.value,
            external_channel_id=normalized.external_channel_id,
            channel_type=normalized.channel_type,
            monitoring_level="B",
            enabled=True,
            silent_mode=silent_mode,
        )
        session.add(channel)
        session.flush()

    conversation = session.scalar(
        select(Conversation).where(
            Conversation.channel_id == channel.id,
            Conversation.external_conversation_id == normalized.external_conversation_id,
        )
    )
    if conversation is None:
        conversation = Conversation(
            channel_id=channel.id,
            external_conversation_id=normalized.external_conversation_id,
        )
        session.add(conversation)
        session.flush()

    identity_id: str | None = None
    if normalized.sender_external_id:
        identity = session.scalar(
            select(Identity).where(
                Identity.platform == Platform.LINE.value,
                Identity.external_identity_id == normalized.sender_external_id,
            )
        )
        if identity is None:
            identity = Identity(
                platform=Platform.LINE.value,
                external_identity_id=normalized.sender_external_id,
            )
            session.add(identity)
            session.flush()
        identity_id = identity.id

    message = Message(
        platform=Platform.LINE.value,
        external_message_id=normalized.external_message_id,
        raw_event_id=raw_event.id,
        channel_id=channel.id,
        conversation_id=conversation.id,
        sender_identity_id=identity_id,
        message_type=normalized.message_type,
        text=normalized.text,
        source_created_at=normalized.source_created_at,
        received_at=datetime.now(UTC),
        processing_status=ProcessingStatus.QUEUED.value,
        metadata_json=normalized.metadata,
    )
    session.add(message)
    session.flush()
    return message


def _event_id(event: dict[str, Any]) -> str:
    webhook_event_id = event.get("webhookEventId")
    if isinstance(webhook_event_id, str) and webhook_event_id:
        return webhook_event_id
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
