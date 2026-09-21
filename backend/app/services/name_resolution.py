from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Channel, Identity, Message, Platform
from app.services.line_profile import LineProfileClient


def resolve_pending_line_names(
    session: Session,
    client: LineProfileClient,
    *,
    limit: int = 30,
) -> dict[str, int]:
    """Fill in display names for LINE identities that only have a user id.

    For each nameless LINE identity we find one of its messages to learn the
    channel (group/room and its id), then ask LINE for the member's display name.
    Names that resolve are stored on the Identity; the rest keep their
    de-identified label. Returns how many were checked and resolved.
    """
    identities = session.scalars(
        select(Identity)
        .where(
            Identity.platform == Platform.LINE.value,
            Identity.display_name.is_(None),
        )
        .limit(limit)
    ).all()

    checked = 0
    resolved = 0
    for identity in identities:
        channel = session.scalar(
            select(Channel)
            .join(Message, Message.channel_id == Channel.id)
            .where(Message.sender_identity_id == identity.id)
            .limit(1)
        )
        if channel is None:
            continue
        checked += 1
        name = client.fetch_display_name(
            channel.channel_type,
            channel.external_channel_id,
            identity.external_identity_id,
        )
        if name:
            identity.display_name = name
            resolved += 1
    session.commit()
    return {"checked": checked, "resolved": resolved}
