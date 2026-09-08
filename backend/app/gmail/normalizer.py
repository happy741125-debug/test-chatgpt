from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import getaddresses
from html.parser import HTMLParser
from typing import Any

WORK_SIGNAL_WORDS = (
    "訂單",
    "出貨",
    "入庫",
    "庫存",
    "急單",
    "客訴",
    "報價",
    "合約",
    "匯款",
    "付款",
    "貨款",
    "應收",
    "對帳",
    "發票",
    "系統異常",
    "wms",
)
MARKETING_WORDS = (
    "電子報",
    "newsletter",
    "edm",
    "優惠",
    "折扣",
    "促銷",
    "立即購買",
    "取消訂閱",
    "unsubscribe",
)


@dataclass(frozen=True)
class NormalizedGmailMessage:
    account_email: str
    external_message_id: str
    external_thread_id: str
    sender_email: str | None
    sender_name: str | None
    subject: str
    text: str
    source_created_at: datetime
    metadata: dict[str, Any]


def normalize_gmail_message(
    account_email: str,
    message: dict[str, Any],
) -> NormalizedGmailMessage | None:
    message_id = message.get("id")
    thread_id = message.get("threadId")
    payload = message.get("payload")
    if not isinstance(message_id, str) or not isinstance(thread_id, str):
        return None
    if not isinstance(payload, dict):
        return None

    headers = _headers(payload)
    sender = getaddresses([headers.get("from", "")])
    sender_name, sender_email = sender[0] if sender else ("", "")
    recipients = [email.lower() for _, email in getaddresses([headers.get("to", "")]) if email]
    cc = [email.lower() for _, email in getaddresses([headers.get("cc", "")]) if email]
    subject = headers.get("subject", "（無主旨）").strip() or "（無主旨）"
    plain_parts, html_parts, has_attachments = _body_parts(payload)
    body = "\n".join(part for part in plain_parts if part).strip()
    if not body and html_parts:
        parser = _TextExtractor()
        parser.feed("\n".join(html_parts))
        body = parser.text()
    cleaned_body = _clean_body(body)
    text = f"主旨：{subject}"
    if cleaned_body:
        text += f"\n{cleaned_body}"

    internal_date = message.get("internalDate")
    try:
        source_created_at = datetime.fromtimestamp(int(str(internal_date)) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        source_created_at = datetime.now(UTC)

    labels = message.get("labelIds", [])
    label_ids = (
        [label for label in labels if isinstance(label, str)] if isinstance(labels, list) else []
    )
    category, work_relevant, classification_reasons = classify_gmail_message(
        account_email=account_email,
        sender_email=sender_email,
        recipients=recipients,
        cc=cc,
        subject=subject,
        body=cleaned_body,
        headers=headers,
        label_ids=label_ids,
    )
    return NormalizedGmailMessage(
        account_email=account_email.lower(),
        external_message_id=message_id,
        external_thread_id=thread_id,
        sender_email=sender_email.lower() if sender_email else None,
        sender_name=sender_name or None,
        subject=subject,
        text=text,
        source_created_at=source_created_at,
        metadata={
            "gmail_message_id": message_id,
            "gmail_thread_id": thread_id,
            "account_email": account_email.lower(),
            "subject": subject,
            "from": sender_email.lower() if sender_email else None,
            "to": recipients,
            "cc": cc,
            "label_ids": label_ids,
            "snippet": str(message.get("snippet") or ""),
            "has_attachments": has_attachments,
            "forwarded": subject.lower().startswith(("fwd:", "fw:")),
            "message_category": category,
            "work_relevant": work_relevant,
            "classification_reasons": classification_reasons,
        },
    )


def classify_gmail_message(
    *,
    account_email: str,
    sender_email: str,
    recipients: list[str],
    cc: list[str],
    subject: str,
    body: str,
    headers: dict[str, str],
    label_ids: list[str],
) -> tuple[str, bool, list[str]]:
    """Conservatively remove obvious bulk mail while keeping operational system mail."""
    combined = f"{subject}\n{body}".casefold()
    has_work_signal = any(word.casefold() in combined for word in WORK_SIGNAL_WORDS)
    reasons: list[str] = []

    bulk_header = bool(headers.get("list-unsubscribe") or headers.get("list-id"))
    bulk_precedence = headers.get("precedence", "").casefold() in {"bulk", "list", "junk"}
    promotional_label = "CATEGORY_PROMOTIONS" in label_ids
    marketing_copy = any(word.casefold() in combined for word in MARKETING_WORDS)
    if bulk_header:
        reasons.append("BULK_HEADER")
    if bulk_precedence:
        reasons.append("BULK_PRECEDENCE")
    if promotional_label:
        reasons.append("PROMOTIONS_LABEL")
    if marketing_copy:
        reasons.append("MARKETING_COPY")
    if (
        bulk_header or bulk_precedence or promotional_label or marketing_copy
    ) and not has_work_signal:
        category = "NEWSLETTER" if bulk_header or bulk_precedence else "MARKETING"
        return category, False, reasons

    auto_submitted = headers.get("auto-submitted", "").casefold()
    automated = auto_submitted not in {"", "no"} or sender_email.casefold().startswith(
        ("no-reply@", "noreply@")
    )
    if automated:
        reasons.append("AUTOMATED_SENDER")
        return "SYSTEM", has_work_signal, reasons

    normalized_account = account_email.casefold()
    if normalized_account in cc and normalized_account not in recipients:
        return "CC", True, ["ACCOUNT_IN_CC"]
    return "PRIMARY", True, ["DIRECT_OR_THREAD_MAIL"]


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    raw_headers = payload.get("headers", [])
    if not isinstance(raw_headers, list):
        return {}
    result: dict[str, str] = {}
    for header in raw_headers:
        if not isinstance(header, dict):
            continue
        name = header.get("name")
        value = header.get("value")
        if isinstance(name, str) and isinstance(value, str):
            result[name.lower()] = value
    return result


def _body_parts(payload: dict[str, Any]) -> tuple[list[str], list[str], bool]:
    plain: list[str] = []
    html: list[str] = []
    has_attachments = False

    def walk(part: dict[str, Any]) -> None:
        nonlocal has_attachments
        filename = part.get("filename")
        if isinstance(filename, str) and filename:
            has_attachments = True
        mime_type = str(part.get("mimeType") or "")
        body = part.get("body")
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, str) and data:
            decoded = _decode_base64url(data)
            if mime_type == "text/plain":
                plain.append(decoded)
            elif mime_type == "text/html":
                html.append(decoded)
        parts = part.get("parts", [])
        if isinstance(parts, list):
            for child in parts:
                if isinstance(child, dict):
                    walk(child)

    walk(payload)
    return plain, html, has_attachments


def _decode_base64url(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding).decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""


def _clean_body(value: str) -> str:
    lines: list[str] = []
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if stripped == "--":
            break
        if re.match(r"^On .+ wrote:$", stripped, re.I):
            break
        if stripped.startswith(("寄件者:", "寄件者：", "From:")) and lines:
            break
        if stripped.startswith(">"):
            continue
        lines.append(line.rstrip())
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()[:12000]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self.parts)).strip()
