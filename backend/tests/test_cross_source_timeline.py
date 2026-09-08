from __future__ import annotations

from datetime import UTC, datetime

from app.models import (
    IntelligenceObject,
    IntelligenceSource,
    Message,
    Platform,
)

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _seed_cross_source_case(database) -> str:  # type: ignore[no-untyped-def]
    """One order case with a LINE message and an earlier Gmail message.

    The Gmail message happened first but is stored with a later evidence_order,
    so a correct timeline must sort by when the message actually happened, not by
    insertion order. FK enforcement is off for the SQLite test database, so the
    upstream rows (context / ai_run / domain) are referenced by id without being
    materialised.
    """
    order_id = "ORD-20260908-5001"
    gmail_time = datetime(2026, 9, 5, 3, 0, tzinfo=UTC)
    line_time = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)
    with database.session_factory() as session:
        card = IntelligenceObject(
            id="intel-cross-1",
            case_key="case-cross-1",
            facets_json=["EVENT"],
            context_id="context-cross-1",
            context_version=1,
            ai_run_id="airun-cross-1",
            fingerprint="fingerprint-cross-1",
            type="EVENT",
            domain_code="WAREHOUSE_OPERATIONS",
            event_type_code="URGENT_ORDER",
            title=f"急單 {order_id}",
            summary="LINE 與 Gmail 都提到同一張急單。",
            confidence=0.9,
            priority_level="P1",
            priority_score=60,
        )
        line_message = Message(
            id="msg-line-1",
            platform=Platform.LINE.value,
            external_message_id="line-ext-1",
            raw_event_id="raw-line-1",
            channel_id="channel-line-1",
            conversation_id="conv-line-1",
            message_type="text",
            text=f"{order_id} 客戶追問今天能不能出貨？",
            source_created_at=line_time,
        )
        gmail_message = Message(
            id="msg-gmail-1",
            platform=Platform.GMAIL.value,
            external_message_id="gmail-ext-1",
            raw_event_id="raw-gmail-1",
            channel_id="channel-gmail-1",
            conversation_id="conv-gmail-1",
            message_type="email",
            text=f"主旨：{order_id} 訂單確認\n客戶已回簽採購單。",
            source_created_at=gmail_time,
        )
        session.add_all([card, line_message, gmail_message])
        session.flush()
        # LINE gets evidence_order 1 even though the Gmail message is older.
        session.add_all(
            [
                IntelligenceSource(
                    intelligence_id=card.id,
                    context_id="context-cross-1",
                    message_id=line_message.id,
                    evidence_order=1,
                ),
                IntelligenceSource(
                    intelligence_id=card.id,
                    context_id="context-cross-1",
                    message_id=gmail_message.id,
                    evidence_order=2,
                ),
            ]
        )
        session.commit()
        return card.id


def test_detail_timeline_is_chronological_across_sources(test_context) -> None:
    client, database, _ = test_context
    card_id = _seed_cross_source_case(database)

    response = client.get(f"/api/intelligence/{card_id}", headers=OPS_HEADERS)
    assert response.status_code == 200
    body = response.json()

    # Timeline follows real time (Gmail 9/5 before LINE 9/8), not evidence_order.
    platforms_in_order = [source["platform"] for source in body["sources"]]
    assert platforms_in_order == [Platform.GMAIL.value, Platform.LINE.value]
    times = [source["source_created_at"] for source in body["sources"]]
    assert times == sorted(times)

    summary = body["cross_source"]
    assert summary["is_cross_source"] is True
    assert summary["platforms"] == [Platform.GMAIL.value, Platform.LINE.value]
    assert summary["source_breakdown"] == {Platform.GMAIL.value: 1, Platform.LINE.value: 1}
    assert summary["timeline_start"] < summary["timeline_end"]

    # The card list view already tells the reader both sources are attached.
    assert body["source_platforms"] == [Platform.GMAIL.value, Platform.LINE.value]


def test_single_source_case_is_not_flagged_cross_source(test_context) -> None:
    client, database, _ = test_context
    order_id = "ORD-20260908-6001"
    with database.session_factory() as session:
        card = IntelligenceObject(
            id="intel-single-1",
            case_key="case-single-1",
            facets_json=["EVENT"],
            context_id="context-single-1",
            context_version=1,
            ai_run_id="airun-single-1",
            fingerprint="fingerprint-single-1",
            type="EVENT",
            domain_code="WAREHOUSE_OPERATIONS",
            event_type_code="URGENT_ORDER",
            title=f"急單 {order_id}",
            summary="只有 LINE 一個來源。",
            confidence=0.8,
        )
        message = Message(
            id="msg-line-single",
            platform=Platform.LINE.value,
            external_message_id="line-ext-single",
            raw_event_id="raw-line-single",
            channel_id="channel-line-single",
            conversation_id="conv-line-single",
            message_type="text",
            text=f"{order_id} 已安排出貨。",
            source_created_at=datetime(2026, 9, 8, 6, 0, tzinfo=UTC),
        )
        session.add_all([card, message])
        session.flush()
        session.add(
            IntelligenceSource(
                intelligence_id=card.id,
                context_id="context-single-1",
                message_id=message.id,
                evidence_order=1,
            )
        )
        session.commit()

    response = client.get(f"/api/intelligence/{card.id}", headers=OPS_HEADERS)
    assert response.status_code == 200
    summary = response.json()["cross_source"]
    assert summary["is_cross_source"] is False
    assert summary["platforms"] == [Platform.LINE.value]
