"""Add configurable warehouse work calendar.

Revision ID: 0026_work_calendar
Revises: 0025_simplified_import_backfill
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_work_calendar"
down_revision: str | None = "0025_simplified_import_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_calendar_settings",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column(
            "closed_weekdays_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[6]'"),
        ),
        sa.Column(
            "holiday_dates_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "working_dates_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("work_calendar_settings")
