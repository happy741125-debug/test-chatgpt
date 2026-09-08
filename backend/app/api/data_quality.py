from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, update

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import Attachment, AttachmentAccessAudit, RawEvent
from app.security.redaction import redact_sensitive_text

router = APIRouter(prefix="/api", tags=["data-quality"])


class AttachmentPreview(BaseModel):
    id: str
    filename: str | None
    media_type: str
    size_bytes: int | None
    processing_status: str
    extracted_text: str | None


class RetentionResult(BaseModel):
    raw_events_purged: int
    attachments_purged: int


@router.get("/attachments/{attachment_id}")
def attachment_preview(
    attachment_id: str,
    _: OpsAccess,
    session: SessionDependency,
) -> AttachmentPreview:
    attachment = session.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail={"error_code": "ATTACHMENT_NOT_FOUND"})
    session.add(
        AttachmentAccessAudit(
            attachment_id=attachment.id,
            actor_text="OPS_USER",
            action="VIEW_EXTRACTED_TEXT",
        )
    )
    extracted = attachment.metadata_json.get("extracted_text")
    session.commit()
    return AttachmentPreview(
        id=attachment.id,
        filename=redact_sensitive_text(attachment.filename),
        media_type=attachment.media_type,
        size_bytes=attachment.size_bytes,
        processing_status=attachment.processing_status,
        extracted_text=redact_sensitive_text(extracted if isinstance(extracted, str) else None),
    )


@router.post("/data-retention/purge")
def purge_expired_data(_: OpsAccess, session: SessionDependency) -> RetentionResult:
    now = datetime.now(UTC)
    attachment_result = session.execute(
        delete(Attachment).where(
            Attachment.retention_until.is_not(None), Attachment.retention_until < now
        )
    )
    raw_result = session.execute(
        update(RawEvent)
        .where(RawEvent.retention_until.is_not(None), RawEvent.retention_until < now)
        .values(payload_json={"purged": True}, retention_until=None)
    )
    session.commit()
    return RetentionResult(
        raw_events_purged=raw_result.rowcount or 0,
        attachments_purged=attachment_result.rowcount or 0,
    )
