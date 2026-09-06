from __future__ import annotations

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

LINE_EVENTS_ACCEPTED = Counter(
    "workhub_line_events_accepted_total",
    "Number of unique LINE events durably accepted.",
)
LINE_EVENTS_DUPLICATE = Counter(
    "workhub_line_events_duplicate_total",
    "Number of LINE event redeliveries ignored as duplicates.",
)
LINE_MESSAGES_CREATED = Counter(
    "workhub_line_messages_created_total",
    "Number of normalized LINE messages created.",
)
LINE_INVALID_SIGNATURES = Counter(
    "workhub_line_invalid_signatures_total",
    "Number of LINE webhook requests rejected for an invalid signature.",
)
QUEUE_PUBLISH_FAILURES = Counter(
    "workhub_queue_publish_failures_total",
    "Number of durable jobs that could not be published immediately.",
)


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
