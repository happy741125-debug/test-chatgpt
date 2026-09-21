from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ai.schemas import ContextAnalysisOutput
from app.intelligence.materializer import IntelligenceMaterializer
from app.models import (
    AIRun,
    AIRunStatus,
    Context,
    Identity,
    Message,
    Person,
    Platform,
)
from app.security.sender import sender_label

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def test_sender_label_prefers_resolved_real_name(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        session.add(Person(id="person-1", display_name="王小明"))
        session.add(
            Identity(
                id="idn-1",
                platform=Platform.LINE.value,
                external_identity_id="Uaaa111",
                person_id="person-1",
            )
        )
        session.commit()
        assert sender_label(session, "idn-1", Platform.LINE.value) == "王小明"


def test_sender_label_uses_identity_display_name(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        session.add(
            Identity(
                id="idn-2",
                platform=Platform.GMAIL.value,
                external_identity_id="vendor@example.com",
                display_name="甲廠商",
            )
        )
        session.commit()
        assert sender_label(session, "idn-2", Platform.GMAIL.value) == "甲廠商"


def test_sender_label_deidentified_code_for_nameless_line(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        session.add(
            Identity(
                id="idn-3",
                platform=Platform.LINE.value,
                external_identity_id="Usecret-userid-xyz",
            )
        )
        session.commit()
        label = sender_label(session, "idn-3", Platform.LINE.value)
        assert label is not None
        assert label.startswith("LINE 成員 ")
        # The raw platform user id is never exposed.
        assert "Usecret-userid-xyz" not in label
        # Stable across calls so the reader can tell speakers apart consistently.
        assert sender_label(session, "idn-3", Platform.LINE.value) == label


def test_sender_label_none_when_no_identity(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        assert sender_label(session, None, Platform.LINE.value) is None
        assert sender_label(session, "missing-id", Platform.LINE.value) is None


def test_timeline_exposes_speaker_on_real_case(test_context) -> None:
    client, database, _ = test_context
    now = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)
    with database.session_factory() as session:
        session.add(
            Identity(
                id="idn-speaker",
                platform=Platform.LINE.value,
                external_identity_id="Uspeaker-userid",
            )
        )
        session.add(
            Context(
                id="ctx-s1",
                channel_id="ch-s1",
                start_at=now,
                end_at=now + timedelta(minutes=5),
                version=1,
            )
        )
        session.add(
            AIRun(
                id="run-s1",
                context_id="ctx-s1",
                context_version=1,
                prompt_version_id="pv-s1",
                provider="rule-based",
                model="test",
                status=AIRunStatus.SUCCEEDED.value,
                requires_review=False,
            )
        )
        session.add(
            Message(
                id="msg-s1",
                platform=Platform.LINE.value,
                external_message_id="ext-s1",
                raw_event_id="raw-s1",
                channel_id="ch-s1",
                conversation_id="conv-s1",
                message_type="text",
                text="有一批商品缺貨了",
                source_created_at=now,
                sender_identity_id="idn-speaker",
            )
        )
        session.commit()

    output = ContextAnalysisOutput.model_validate(
        {
            "work_related": True,
            "noise_type": None,
            "summary": "缺貨案件測試摘要。",
            "entities": [],
            "items": [
                {
                    "type": "EVENT",
                    "domain_code": "WAREHOUSE_OPERATIONS",
                    "event_type_code": "STOCK_SHORTAGE",
                    "title": "缺貨事件",
                    "summary": "測試事件。",
                    "owner_text": None,
                    "deadline": None,
                    "requires_user_action": False,
                    "evidence_message_ids": ["msg-s1"],
                    "confidence": 0.9,
                }
            ],
            "overall_confidence": 0.9,
        }
    )
    card_id = IntelligenceMaterializer(database.session_factory).materialize("ctx-s1", output)[0]

    detail = client.get(f"/api/intelligence/{card_id}", headers=OPS_HEADERS).json()
    senders = [source["sender"] for source in detail["sources"]]
    # The nameless LINE speaker still surfaces as a de-identified, stable label.
    assert any(sender and sender.startswith("LINE 成員 ") for sender in senders)
