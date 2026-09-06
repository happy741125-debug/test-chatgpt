from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import Context, ContextMessage, Message

router = APIRouter(prefix="/api/contexts", tags=["contexts"])


class ContextSourceMessage(BaseModel):
    id: str
    sequence: int
    sender_identity_id: str | None
    message_type: str
    text: str | None
    source_created_at: datetime


class ContextDetail(BaseModel):
    id: str
    channel_id: str
    start_at: datetime
    end_at: datetime
    status: str
    version: int
    token_estimate: int
    message_count: int
    urgent_bypass: bool
    messages: list[ContextSourceMessage]


@router.get("/{context_id}")
def get_context(context_id: str, _: OpsAccess, session: SessionDependency) -> ContextDetail:
    context = session.get(Context, context_id)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CONTEXT_NOT_FOUND"},
        )

    rows = session.execute(
        select(ContextMessage, Message)
        .join(Message, Message.id == ContextMessage.message_id)
        .where(ContextMessage.context_id == context_id)
        .order_by(ContextMessage.sequence)
    ).all()
    messages = [
        ContextSourceMessage(
            id=message.id,
            sequence=link.sequence,
            sender_identity_id=message.sender_identity_id,
            message_type=message.message_type,
            text=message.text,
            source_created_at=message.source_created_at,
        )
        for link, message in rows
    ]
    return ContextDetail(
        id=context.id,
        channel_id=context.channel_id,
        start_at=context.start_at,
        end_at=context.end_at,
        status=context.status,
        version=context.version,
        token_estimate=context.token_estimate,
        message_count=context.message_count,
        urgent_bypass=context.urgent_bypass,
        messages=messages,
    )
