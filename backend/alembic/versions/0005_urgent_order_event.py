"""Add urgent order event type.

Revision ID: 0005_urgent_order_event
Revises: 0004_domain_intelligence
Create Date: 2026-09-07
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0005_urgent_order_event"
down_revision: str | None = "0004_domain_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    event_types = sa.table(
        "event_types",
        sa.column("code", sa.String),
        sa.column("domain_code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        event_types,
        [
            {
                "code": "URGENT_ORDER",
                "domain_code": "WAREHOUSE_OPERATIONS",
                "name": "急單／緊急出貨",
                "description": "急單、插單、趕單及有明確時限的緊急出貨需求",
                "active": True,
                "created_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE intelligence_objects "
            "SET event_type_code = 'UNKNOWN' "
            "WHERE event_type_code = 'URGENT_ORDER'"
        )
    )
    op.execute(sa.text("DELETE FROM event_types WHERE code = 'URGENT_ORDER'"))
