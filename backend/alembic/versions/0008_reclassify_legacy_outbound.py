"""Correct legacy outbound updates that were classified as urgent orders.

Revision ID: 0008_reclassify_legacy_outbound
Revises: 0007_operational_case_cards
Create Date: 2026-09-07
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_reclassify_legacy_outbound"
down_revision: str | None = "0007_operational_case_cards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _reclassify_legacy_outbound(op.get_bind())


def downgrade() -> None:
    # Historical corrections are intentionally not changed back to a known false classification.
    pass


def _reclassify_legacy_outbound(bind: sa.Connection) -> None:
    bind.execute(
        sa.text(
            """
            UPDATE intelligence_objects
            SET event_type_code = 'OUTBOUND_OPERATION',
                title = '出入庫作業進度更新',
                type = 'EVENT',
                facets_json = :facets,
                deadline_raw_text = CASE
                    WHEN summary LIKE '%今日%' THEN '今日'
                    WHEN summary LIKE '%今天%' THEN '今天'
                    ELSE deadline_raw_text
                END,
                priority_score = 35,
                priority_level = 'P2',
                priority_reasons_json = :reasons
            WHERE status != 'ARCHIVED'
              AND event_type_code = 'URGENT_ORDER'
              AND (
                  summary LIKE '%安排出貨%'
                  OR summary LIKE '%今日出貨%'
                  OR summary LIKE '%明天出貨%'
              )
              AND summary NOT LIKE '%急單%'
              AND summary NOT LIKE '%插單%'
              AND summary NOT LIKE '%趕單%'
              AND summary NOT LIKE '%務必%'
              AND summary NOT LIKE '%緊急%'
              AND summary NOT LIKE '%優先%'
            """
        ),
        {
            "facets": json.dumps(["EVENT", "TASK", "COMMITMENT"]),
            "reasons": json.dumps(
                [
                    {"code": "DEADLINE_URGENCY", "score": 10},
                    {"code": "BUSINESS_IMPACT", "score": 20},
                    {"code": "HAS_DEADLINE", "score": 5},
                ]
            ),
        },
    )
