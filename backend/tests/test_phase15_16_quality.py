from __future__ import annotations

import base64
from datetime import UTC, datetime

from sqlalchemy import select

from app.ai.order_ids import extract_order_ids
from app.intelligence.case_matching import find_review_candidate
from app.models import (
    Attachment,
    AttachmentAccessAudit,
    CaseMergeAudit,
    CaseReviewItem,
    IntelligenceObject,
    IntelligenceSource,
    Message,
    Platform,
)
from app.security.redaction import redact_sensitive_text
from app.services.gmail_ingestion import ingest_gmail_message

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _card(card_id: str, title: str, summary: str) -> IntelligenceObject:
    return IntelligenceObject(
        id=card_id,
        case_key=f"case-{card_id}",
        context_id=f"context-{card_id}",
        context_version=1,
        ai_run_id=f"run-{card_id}",
        fingerprint=f"fingerprint-{card_id}",
        facets_json=["EVENT"],
        type="EVENT",
        domain_code="WAREHOUSE_OPERATIONS",
        event_type_code="URGENT_ORDER",
        title=title,
        summary=summary,
        confidence=0.9,
        priority_score=50,
        priority_level="P1",
    )


def _message(message_id: str, text: str) -> Message:
    return Message(
        id=message_id,
        platform=Platform.LINE.value,
        external_message_id=f"external-{message_id}",
        raw_event_id=f"raw-{message_id}",
        channel_id="channel-test",
        conversation_id="conversation-test",
        message_type="text",
        text=text,
        source_created_at=datetime.now(UTC),
    )


def test_gmail_attachment_metadata_is_saved_without_binary(test_context) -> None:
    _, database, _ = test_context
    encoded = base64.urlsafe_b64encode("安全測試內容".encode()).decode().rstrip("=")
    payload = {
        "id": "gmail-with-attachment",
        "threadId": "thread-with-attachment",
        "internalDate": "4102444800000",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "測試客戶 <customer@example.com>"},
                {"name": "To", "value": "ops@example.com"},
                {"name": "Subject", "value": "入庫資料"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": encoded}},
                {
                    "filename": "sample.csv",
                    "mimeType": "text/csv",
                    "body": {"attachmentId": "attachment-1", "size": 512},
                },
            ],
        },
    }
    with database.session_factory() as session:
        result = ingest_gmail_message(session, "ops@example.com", payload)
        attachment = session.scalar(select(Attachment))

    assert result.created is True
    assert attachment is not None
    assert attachment.filename == "sample.csv"
    assert attachment.size_bytes == 512
    assert attachment.processing_status == "METADATA_ONLY"
    assert attachment.retention_until is not None


def test_dashboard_evidence_masks_contact_and_credentials(test_context) -> None:
    client, database, _ = test_context
    with database.session_factory() as session:
        card = _card("private", "付款確認", "等待客戶回覆")
        message = _message(
            "private-message",
            "聯絡 customer@example.com 或 0912-345-678\npassword: do-not-show",
        )
        session.add_all([card, message])
        session.flush()
        session.add(
            IntelligenceSource(
                intelligence_id=card.id,
                context_id=card.context_id,
                message_id=message.id,
                evidence_order=1,
            )
        )
        session.commit()

    response = client.get("/api/intelligence/private", headers=OPS_HEADERS)
    text = response.json()["sources"][0]["text"]
    assert "customer@example.com" not in text
    assert "0912-345-678" not in text
    assert "do-not-show" not in text


def test_source_health_reports_both_sources(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/api/sources/health", headers=OPS_HEADERS)

    assert response.status_code == 200
    assert [item["platform"] for item in response.json()["sources"]] == ["LINE", "GMAIL"]


def test_reference_extraction_supports_work_and_case_ids() -> None:
    assert extract_order_ids("請追蹤 WO-20260908-123 與 CASE-ABC-9988") == [
        "WO-20260908-123",
        "CASE-ABC-9988",
    ]


def test_similar_no_id_case_enters_review_instead_of_auto_merge(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        first = _card("candidate", "收到急單／緊急出貨需求", "兩筆急單明天務必出貨")
        second = _card("incoming", "收到急單／緊急出貨需求", "兩筆急單明天需要完成出貨")
        session.add_all([first, second])
        session.flush()
        match = find_review_candidate(session, second)

    assert match is not None
    assert match.candidate_id == "candidate"
    assert match.score >= 0.68


def test_manual_merge_and_unmerge_preserve_audit_trail(test_context) -> None:
    client, database, _ = test_context
    with database.session_factory() as session:
        source = _card("source", "急單後續", "今天確認出貨")
        target = _card("target", "收到急單", "明天務必出貨")
        source_message = _message("source-evidence", "今天確認出貨")
        target_message = _message("target-evidence", "明天務必出貨")
        session.add_all([source, target, source_message, target_message])
        session.flush()
        session.add_all(
            [
                IntelligenceSource(
                    intelligence_id=source.id,
                    context_id=source.context_id,
                    message_id=source_message.id,
                    evidence_order=1,
                ),
                IntelligenceSource(
                    intelligence_id=target.id,
                    context_id=target.context_id,
                    message_id=target_message.id,
                    evidence_order=1,
                ),
                CaseReviewItem(
                    id="review-1",
                    intelligence_id=source.id,
                    candidate_intelligence_id=target.id,
                    score=0.88,
                    reasons_json=[{"code": "TEXT_SIMILARITY", "value": 0.9}],
                ),
            ]
        )
        session.commit()

    merged = client.post(
        "/api/case-reviews/review-1/resolve",
        headers=OPS_HEADERS,
        json={"action": "MERGE", "target_id": "target"},
    )
    assert merged.status_code == 200
    audit_id = merged.json()["merge_audit_id"]
    with database.session_factory() as session:
        assert session.get(IntelligenceObject, "source").status == "ARCHIVED"
        assert session.get(CaseMergeAudit, audit_id) is not None
        target_sources = session.scalars(
            select(IntelligenceSource).where(IntelligenceSource.intelligence_id == "target")
        ).all()
        assert len(target_sources) == 2

    reversed_response = client.post(
        f"/api/case-merges/{audit_id}/unmerge", headers=OPS_HEADERS
    )
    assert reversed_response.status_code == 200
    with database.session_factory() as session:
        assert session.get(IntelligenceObject, "source").status == "OPEN"
        target_sources = session.scalars(
            select(IntelligenceSource).where(IntelligenceSource.intelligence_id == "target")
        ).all()
        assert len(target_sources) == 1


def test_redaction_keeps_operational_reference_ids() -> None:
    text = "ORD-20260908-0001，請回 customer@example.com"
    assert redact_sensitive_text(text) == "ORD-20260908-0001，請回 [Email 已遮蔽]"


def test_attachment_preview_requires_ops_access_and_records_audit(test_context) -> None:
    client, database, _ = test_context
    with database.session_factory() as session:
        message = _message("attachment-source", "請查看附件")
        session.add(message)
        session.flush()
        attachment = Attachment(
            id="attachment-preview",
            message_id=message.id,
            platform="GMAIL",
            external_attachment_id="gmail-attachment",
            filename="contact-customer@example.com.txt",
            media_type="text/plain",
            processing_status="TEXT_EXTRACTED",
            metadata_json={"extracted_text": "請聯絡 0912-345-678"},
        )
        session.add(attachment)
        session.commit()

    denied = client.get("/api/attachments/attachment-preview")
    assert denied.status_code == 403
    allowed = client.get("/api/attachments/attachment-preview", headers=OPS_HEADERS)
    assert allowed.status_code == 200
    assert "customer@example.com" not in allowed.json()["filename"]
    assert "0912-345-678" not in allowed.json()["extracted_text"]
    with database.session_factory() as session:
        assert session.scalar(select(AttachmentAccessAudit)) is not None
