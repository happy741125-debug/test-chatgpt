from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import Channel

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    external_channel_id: str
    name: str | None
    channel_type: str
    company_id: str | None
    project_id: str | None
    monitoring_level: str
    enabled: bool
    silent_mode: bool


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    company_id: str | None = Field(default=None, max_length=36)
    project_id: str | None = Field(default=None, max_length=36)
    monitoring_level: Literal["A", "B", "C", "D"] | None = None
    enabled: bool | None = None


@router.get("")
def list_channels(_: OpsAccess, session: SessionDependency) -> list[ChannelResponse]:
    channels = session.scalars(select(Channel).order_by(Channel.created_at.desc())).all()
    return [ChannelResponse.model_validate(channel) for channel in channels]


@router.get("/{channel_id}")
def get_channel(channel_id: str, _: OpsAccess, session: SessionDependency) -> ChannelResponse:
    return ChannelResponse.model_validate(_get_channel_or_404(session, channel_id))


@router.patch("/{channel_id}")
def update_channel(
    channel_id: str,
    update: ChannelUpdate,
    _: OpsAccess,
    session: SessionDependency,
) -> ChannelResponse:
    channel = _get_channel_or_404(session, channel_id)
    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(channel, field_name, value)
    session.commit()
    session.refresh(channel)
    return ChannelResponse.model_validate(channel)


def _get_channel_or_404(session, channel_id: str) -> Channel:
    channel = session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CHANNEL_NOT_FOUND"},
        )
    return channel
