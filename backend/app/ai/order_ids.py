from __future__ import annotations

import re

# Reference-id formats seen across real 貨達 conversations:
#   - New system order:  ORD-20260731-0001
#   - Inbound sheet:      INB-20260826-0001
#   - Legacy system id:   1042H2608240006 / 1026H2606030002 (digits + H + digits)
# These identify a case so the same order/inbound merges across LINE and Gmail.
_PATTERNS = (
    re.compile(r"\bORD-[A-Z0-9-]+\b", re.IGNORECASE),
    re.compile(r"\bINB-[A-Z0-9-]+\b", re.IGNORECASE),
    re.compile(r"\b\d{3,4}H\d{6,}\b", re.IGNORECASE),
    re.compile(r"\bWO-[A-Z0-9-]{5,}\b", re.IGNORECASE),
    re.compile(r"\b(?:REF|CASE|TICKET)-[A-Z0-9-]{5,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{2,5}\d{8,18}\b", re.IGNORECASE),
)


def extract_order_ids(text: str) -> list[str]:
    """Return the reference ids found in text, upper-cased and de-duplicated."""
    found: list[str] = []
    for pattern in _PATTERNS:
        found.extend(match.upper() for match in pattern.findall(text))
    return list(dict.fromkeys(found))
