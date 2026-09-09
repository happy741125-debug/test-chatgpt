from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models import (
    Domain,
    IntelligenceHistoryEvent,
    IntelligenceObject,
)

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _seed(database) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    with database.session_factory() as session:
        # Config that must survive the reset.
        session.add(Domain(code="WAREHOUSE_OPERATIONS", name="倉儲營運", description="測試"))
        card = IntelligenceObject(
            id="card-reset",
            case_key="key-reset",
            facets_json=["EVENT"],
            context_id="c",
            context_version=1,
            ai_run_id="r",
            fingerprint="fp",
            type="EVENT",
            domain_code="WAREHOUSE_OPERATIONS",
            event_type_code="STOCK_SHORTAGE",
            title="測試卡",
            summary="測試",
            confidence=0.8,
            created_at=now,
            last_changed_at=now,
        )
        session.add(card)
        session.flush()
        session.add(
            IntelligenceHistoryEvent(
                intelligence_id="card-reset",
                event_type="NEW",
                occurred_at=now,
                actor_text="SYSTEM",
                evidence_message_ids_json=[],
                snapshot_json={},
            )
        )
        session.commit()


def test_reset_requires_ops_token(test_context) -> None:
    client, _, _ = test_context
    response = client.post("/api/admin/reset-intelligence", json={"confirm": "CLEAR-TEST-DATA"})
    assert response.status_code == 403


def test_reset_requires_confirm_phrase(test_context) -> None:
    client, database, _ = test_context
    _seed(database)
    bad = client.post("/api/admin/reset-intelligence", headers=OPS_HEADERS, json={"confirm": "yes"})
    assert bad.status_code == 400
    # Nothing deleted.
    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(IntelligenceObject)) == 1


def test_reset_clears_pipeline_but_keeps_config(test_context) -> None:
    client, database, _ = test_context
    _seed(database)

    response = client.post(
        "/api/admin/reset-intelligence",
        headers=OPS_HEADERS,
        json={"confirm": "CLEAR-TEST-DATA"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"]["intelligence_objects"] == 1
    assert body["deleted"]["intelligence_history_events"] == 1
    assert body["total_deleted"] >= 2

    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(IntelligenceObject)) == 0
        assert session.scalar(select(func.count()).select_from(IntelligenceHistoryEvent)) == 0
        # Config kept.
        assert session.scalar(select(func.count()).select_from(Domain)) == 1
