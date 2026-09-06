from __future__ import annotations

import base64
import hashlib
import hmac


def make_signature(body: bytes, channel_secret: str) -> str:
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_signature(body: bytes, signature: str | None, channel_secret: str) -> bool:
    if not signature or not channel_secret:
        return False
    expected = make_signature(body, channel_secret)
    return hmac.compare_digest(expected, signature)
