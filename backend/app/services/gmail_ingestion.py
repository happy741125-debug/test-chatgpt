from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.gmail.normalizer import normalize_gmail_message
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
class GmailIngestionResult:
    created: bool = False
    duplicate: bool = False
    unsupported: bool = False
    message_id: str | None = None
    job_ids: list[str] = field(default_factory=list)


def ingest_gmail_message(
    session: Session,
    account_email: str,
    payload: dict[str, Any],
) -> GmailIngestionResult:
    normalized = normalize_gmail_message(account_email, payload)
    if normalized is None:
        return GmailIngestionResult(unsupported=True)

    external_id = f"{normalized.account_email}:{normalized.external_message_id}"
    existing = session.scalar(
        select(Message.id).where(
            Message.platform == Platform.GMAIL.value,
            Message.external_message_id == external_id,
        )
    )
    if existing is not None:
        return GmailIngestionResult(duplicate=True, message_id=existing)

    try:
        with session.begin_nested():
            raw_event = RawEvent(
                platform=Platform.GMAIL.value,
                external_event_id=external_id,
                payload_json=payload,
                signature_valid=True,
                processing_status=ProcessingStatus.RECEIVED.value,
            )
            session.add(raw_event)
            session.flush()
    except IntegrityError:
        return GmailIngestionResult(duplicate=True)

    channel = _channel(session, normalized.account_email)
    conversation = _conversation(
        session,
        channel.id,
        f"{normalized.account_email}:{normalized.external_thread_id}",
    )
    identity_id = _identity(
        session,
        normalized.sender_email,
        normalized.sender_name,
    )
    message = Message(
        platform=Platform.GMAIL.value,
        external_message_id=external_id,
        raw_event_id=raw_event.id,
        channel_id=channel.id,
        conversation_id=conversation.id,
        sender_identity_id=identity_id,
        message_type="email",
        text=normalized.text,
        source_created_at=normalized.source_created_at,
        received_at=datetime.now(UTC),
        processing_status=(
            ProcessingStatus.QUEUED.value
            if normalized.metadata.get("work_relevant", True)
            else ProcessingStatus.PROCESSED.value
        ),
        metadata_json=normalized.metadata,
    )
    session.add(message)
    session.flush()
    job_ids: list[str] = []
    if normalized.metadata.get("work_relevant", True):
        job = ProcessingJob(
            job_type="build_context",
            idempotency_key=f"build_context:{message.id}",
            payload_json={"message_id": message.id, "channel_id": channel.id},
        )
        session.add(job)
        session.flush()
        job_ids.append(job.id)
        raw_event.processing_status = ProcessingStatus.QUEUED.value
    else:
        raw_event.processing_status = ProcessingStatus.PROCESSED.value
    session.commit()
    return GmailIngestionResult(created=True, message_id=message.id, job_ids=job_ids)


def _channel(session: Session, account_email: str) -> Channel:
    channel = session.scalar(
        select(Channel).where(
            Channel.platform == Platform.GMAIL.value,
            Channel.external_channel_id == account_email,
        )
    )
    if channel is None:
        channel = Channel(
            platform=Platform.GMAIL.value,
            external_channel_id=account_email,
            name=account_email,
            channel_type="EMAIL_ACCOUNT",
            monitoring_level="B",
            enabled=True,
            silent_mode=True,
        )
        session.add(channel)
        session.flush()
    return channel


def _conversation(session: Session, channel_id: str, external_thread_id: str) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.channel_id == channel_id,
            Conversation.external_conversation_id == external_thread_id,
        )
    )
    if conversation is None:
        conversation = Conversation(
            channel_id=channel_id,
            external_conversation_id=external_thread_id,
        )
        session.add(conversation)
        session.flush()
    return conversation


def _identity(
    session: Session,
    email: str | None,
    display_name: str | None,
) -> str | None:
    if email is None:
        return None
    identity = session.scalar(
        select(Identity).where(
            Identity.platform == Platform.GMAIL.value,
            Identity.external_identity_id == email,
        )
    )
    if identity is None:
        identity = Identity(
            platform=Platform.GMAIL.value,
            external_identity_id=email,
            display_name=display_name,
        )
        session.add(identity)
        session.flush()
    elif display_name and not identity.display_name:
        identity.display_name = display_name
    return identity.id
