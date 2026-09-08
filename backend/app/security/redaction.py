from __future__ import annotations

import re

_EMAIL = re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE = re.compile(r"(?<!\d)(?:\+?886[-\s]?)?0?9\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)")
_LANDLINE = re.compile(r"(?<!\d)0\d{1,2}[-\s]?\d{6,8}(?!\d)")
_SECRET_LINE = re.compile(
    r"(?im)^.*(?:password|passwd|密碼|token|access[ _-]?key|secret).{0,24}[:=：].*$"
)
_SENSITIVE_URL = re.compile(
    r"https?://\S*(?:token|secret|invite|auth|reset|password)\S*", re.IGNORECASE
)


def redact_sensitive_text(value: str | None) -> str | None:
    """Hide common credentials and personal contact details in dashboard evidence."""
    if value is None:
        return None
    redacted = _SECRET_LINE.sub("[敏感憑證已遮蔽]", value)
    redacted = _SENSITIVE_URL.sub("[敏感連結已遮蔽]", redacted)
    redacted = _EMAIL.sub("[Email 已遮蔽]", redacted)
    redacted = _PHONE.sub("[手機已遮蔽]", redacted)
    return _LANDLINE.sub("[電話已遮蔽]", redacted)
