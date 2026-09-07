"""Collapse intelligence facets into one operational case card.

Revision ID: 0007_operational_case_cards
Revises: 0006_gmail_foundation
Create Date: 2026-09-07
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_operational_case_cards"
down_revision: str | None = "0006_gmail_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORDER_PATTERN = re.compile(r"\bORD-[A-Z0-9-]+\b", re.IGNORECASE)
_TYPE_ORDER = {
    "DECISION_REQUIRED": 0,
    "EVENT": 1,
    "TASK": 2,
    "RISK": 3,
    "COMMITMENT": 4,
    "FOLLOW_UP": 5,
    "DECISION": 6,
    "FYI": 7,
}


def upgrade() -> None:
    with op.batch_alter_table("intelligence_objects") as batch_op:
        batch_op.add_column(sa.Column("case_key", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column("facets_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.create_unique_constraint("uq_intelligence_case_key", ["case_key"])

    event_types = sa.table(
        "event_types",
        sa.column("code", sa.String),
        sa.column("domain_code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT code FROM event_types WHERE code = 'OUTBOUND_OPERATION'")
    ).first()
    if existing is None:
        bind.execute(
            event_types.insert().values(
                code="OUTBOUND_OPERATION",
                domain_code="WAREHOUSE_OPERATIONS",
                name="出入庫作業",
                description="一般入庫、庫存整理與出貨安排",
                active=True,
                created_at=sa.func.now(),
            )
        )

    _collapse_existing_cards(bind)


def downgrade() -> None:
    with op.batch_alter_table("intelligence_objects") as batch_op:
        batch_op.drop_constraint("uq_intelligence_case_key", type_="unique")
        batch_op.drop_column("facets_json")
        batch_op.drop_column("case_key")


def _collapse_existing_cards(bind: sa.Connection) -> None:
    rows = (
        bind.execute(
            sa.text(
                """
            SELECT i.id, i.context_id, i.context_version, i.type, i.title, i.summary,
                   i.status, i.owner_text, i.deadline_at, i.deadline_raw_text,
                   i.requires_user_action, i.confidence, i.priority_score,
                   i.priority_level, i.priority_reasons_json, i.created_at
            FROM intelligence_objects i
            ORDER BY i.created_at, i.id
            """
            )
        )
        .mappings()
        .all()
    )
    source_rows = (
        bind.execute(
            sa.text(
                """
                SELECT s.intelligence_id, m.text
                FROM intelligence_sources s
                JOIN messages m ON m.id = s.message_id
                """
            )
        )
        .mappings()
        .all()
    )
    source_text: dict[str, list[str]] = defaultdict(list)
    for source in source_rows:
        if source["text"]:
            source_text[source["intelligence_id"]].append(source["text"])
    groups: dict[str, list[sa.RowMapping]] = defaultdict(list)
    for row in rows:
        text = " ".join((row["title"] or "", row["summary"] or "", *source_text[row["id"]]))
        order_ids = sorted({match.upper() for match in _ORDER_PATTERN.findall(text)})
        identity = (
            "orders:" + ",".join(order_ids)
            if order_ids
            else f"context:{row['context_id']}:{row['context_version']}"
        )
        groups[_digest(identity)].append(row)

    for case_key, members in groups.items():
        active = [row for row in members if row["status"] not in {"ARCHIVED", "CANCELLED"}]
        candidates = active or members
        survivor = min(
            candidates, key=lambda row: (_TYPE_ORDER.get(row["type"], 99), row["created_at"])
        )
        facets = sorted(
            {row["type"] for row in active}, key=lambda value: _TYPE_ORDER.get(value, 99)
        )
        priority = max(candidates, key=lambda row: int(row["priority_score"] or 0))
        owner = next((row["owner_text"] for row in candidates if row["owner_text"]), None)
        deadlines = [row for row in candidates if row["deadline_at"] is not None]
        deadline = min(deadlines, key=lambda row: row["deadline_at"]) if deadlines else None
        confidence = max(float(row["confidence"] or 0) for row in candidates)
        bind.execute(
            sa.text(
                """
                UPDATE intelligence_objects
                SET case_key = :case_key, facets_json = :facets, owner_text = :owner,
                    deadline_at = :deadline_at, deadline_raw_text = :deadline_raw_text,
                    requires_user_action = :requires_user_action,
                    confidence = :confidence, priority_score = :priority_score,
                    priority_level = :priority_level, priority_reasons_json = :priority_reasons
                WHERE id = :id
                """
            ),
            {
                "case_key": case_key,
                "facets": json.dumps(facets),
                "owner": owner,
                "deadline_at": deadline["deadline_at"] if deadline else None,
                "deadline_raw_text": deadline["deadline_raw_text"] if deadline else None,
                "requires_user_action": any(
                    bool(row["requires_user_action"]) for row in candidates
                ),
                "confidence": confidence,
                "priority_score": priority["priority_score"],
                "priority_level": priority["priority_level"],
                "priority_reasons": _json_text(priority["priority_reasons_json"]),
                "id": survivor["id"],
            },
        )
        for row in members:
            if row["id"] == survivor["id"]:
                continue
            _copy_sources(bind, row["id"], survivor["id"])
            bind.execute(
                sa.text("UPDATE intelligence_objects SET status = 'ARCHIVED' WHERE id = :id"),
                {"id": row["id"]},
            )


def _copy_sources(bind: sa.Connection, source_id: str, survivor_id: str) -> None:
    sources = (
        bind.execute(
            sa.text(
                "SELECT context_id, message_id, evidence_order FROM intelligence_sources "
                "WHERE intelligence_id = :source_id ORDER BY evidence_order"
            ),
            {"source_id": source_id},
        )
        .mappings()
        .all()
    )
    for source in sources:
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM intelligence_sources "
                "WHERE intelligence_id = :survivor_id AND message_id = :message_id"
            ),
            {"survivor_id": survivor_id, "message_id": source["message_id"]},
        ).first()
        if exists is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO intelligence_sources
                        (id, intelligence_id, context_id, message_id, evidence_order, created_at)
                    VALUES
                        (:id, :survivor_id, :context_id, :message_id,
                         :evidence_order, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "survivor_id": survivor_id,
                    "context_id": source["context_id"],
                    "message_id": source["message_id"],
                    "evidence_order": source["evidence_order"],
                },
            )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_text(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value)
