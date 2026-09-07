from __future__ import annotations

import runpy
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, IntelligenceObject


def test_existing_duplicate_cards_are_archived_into_one_case() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                _card("event-card", "EVENT", 45, "P2"),
                _card("task-card", "TASK", 65, "P1"),
            ]
        )
        session.commit()

    migration_path = (
        Path(__file__).parents[1] / "alembic" / "versions" / "0007_operational_case_cards.py"
    )
    collapse = runpy.run_path(str(migration_path))["_collapse_existing_cards"]
    with engine.begin() as connection:
        collapse(connection)

    with Session(engine) as session:
        cards = session.scalars(select(IntelligenceObject).order_by(IntelligenceObject.id)).all()
        survivor = next(card for card in cards if card.id == "event-card")
        duplicate = next(card for card in cards if card.id == "task-card")
        assert survivor.case_key is not None
        assert survivor.facets_json == ["EVENT", "TASK"]
        assert survivor.priority_score == 65
        assert survivor.priority_level == "P1"
        assert duplicate.status == "ARCHIVED"


def _card(card_id: str, item_type: str, score: int, level: str) -> IntelligenceObject:
    return IntelligenceObject(
        id=card_id,
        context_id="context-1",
        context_version=1,
        ai_run_id="run-1",
        fingerprint=f"fingerprint-{card_id}",
        type=item_type,
        domain_code="WAREHOUSE_OPERATIONS",
        event_type_code="URGENT_ORDER",
        title="收到急單 ORD-20260907-0003",
        summary="明天務必安排 ORD-20260907-0003 出貨。",
        owner_text=None,
        deadline_at=None,
        deadline_raw_text="明天",
        requires_user_action=False,
        confidence=0.9,
        priority_score=score,
        priority_level=level,
        priority_reasons_json=[],
        requires_review=False,
    )
