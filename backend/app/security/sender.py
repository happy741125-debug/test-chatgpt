from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.models import Identity, Person, Platform

_PLATFORM_LABELS = {Platform.LINE.value: "LINE", Platform.GMAIL.value: "Gmail"}


def sender_label(session: Session, sender_identity_id: str | None, platform: str) -> str | None:
    """Readable speaker label for a message.

    Prefers a resolved real name (Person > Identity.display_name). When no name is
    known — the usual case for LINE, whose webhook only gives an opaque user id — it
    returns a stable, de-identified short code (e.g. "LINE 成員 A3F2") so the reader
    can still tell speakers apart without the raw platform user id ever being exposed.
    """
    if not sender_identity_id:
        return None
    identity = session.get(Identity, sender_identity_id)
    if identity is None:
        return None
    if identity.person_id:
        person = session.get(Person, identity.person_id)
        if person and person.display_name:
            return person.display_name
    if identity.display_name:
        return identity.display_name
    code = hashlib.sha1(identity.external_identity_id.encode("utf-8")).hexdigest()[:4].upper()
    return f"{_PLATFORM_LABELS.get(platform, platform)} 成員 {code}"
