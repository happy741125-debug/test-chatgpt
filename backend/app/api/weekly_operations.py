from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import (
    GoWarehouseOperationalRecord,
    IntelligenceHistoryEvent,
    IntelligenceObject,
    WeeklyOperationsInput,
)

router = APIRouter(prefix="/api/weekly-operations", tags=["weekly-operations"])
TAIPEI = ZoneInfo("Asia/Taipei")


class WeeklyOperationsPayload(BaseModel):
    week_start: date
    warehouse: str = Field(min_length=1, max_length=80)
    labor_hours: float | None = Field(default=None, ge=0)
    processing_quantity: int | None = Field(default=None, ge=0)
    consumables_inventory_note: str | None = Field(default=None, max_length=1000)
    inventory_count_quantity: int | None = Field(default=None, ge=0)
    inventory_variance_quantity: int | None = Field(default=None)
    pallet_placement_note: str | None = Field(default=None, max_length=1000)


class WeeklyOperationsResponse(WeeklyOperationsPayload):
    id: str


@router.put("")
def save_weekly_input(
    payload: WeeklyOperationsPayload,
    _: OpsAccess,
    session: SessionDependency,
) -> WeeklyOperationsResponse:
    warehouse = payload.warehouse.strip()
    record = session.scalar(
        select(WeeklyOperationsInput).where(
            WeeklyOperationsInput.week_start == payload.week_start,
            WeeklyOperationsInput.warehouse == warehouse,
        )
    )
    values = payload.model_dump()
    values["warehouse"] = warehouse
    if record is None:
        record = WeeklyOperationsInput(**values)
        session.add(record)
    else:
        for field, value in values.items():
            setattr(record, field, value)
    session.commit()
    session.refresh(record)
    return _weekly_response(record)


@router.get("")
def list_weekly_inputs(
    _: OpsAccess,
    session: SessionDependency,
    limit: int = Query(default=24, ge=1, le=104),
) -> list[WeeklyOperationsResponse]:
    rows = session.scalars(
        select(WeeklyOperationsInput)
        .order_by(WeeklyOperationsInput.week_start.desc(), WeeklyOperationsInput.warehouse)
        .limit(limit)
    ).all()
    return [_weekly_response(row) for row in rows]


@router.get("/execution-summary")
def execution_summary(
    _: OpsAccess,
    session: SessionDependency,
    week_start: date,
) -> dict[str, object]:
    week_end = week_start + timedelta(days=6)
    window_start = datetime.combine(week_start, time.min, TAIPEI).astimezone(UTC)
    window_end = datetime.combine(week_end + timedelta(days=1), time.min, TAIPEI).astimezone(UTC)
    events = session.scalars(
        select(IntelligenceHistoryEvent).where(
            IntelligenceHistoryEvent.occurred_at >= window_start,
            IntelligenceHistoryEvent.occurred_at < window_end,
        )
    ).all()
    latest = {event.intelligence_id: event for event in events}
    cards = {
        card.id: card
        for card in session.scalars(
            select(IntelligenceObject).where(
                IntelligenceObject.id.in_(list(latest) or ["__none__"])
            )
        ).all()
    }
    by_domain: dict[str, int] = {}
    by_type: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for card_id, event in latest.items():
        card = cards.get(card_id)
        snapshot = event.snapshot_json or {}
        attention = str(snapshot.get("attention_level") or (card.attention_level if card else ""))
        if attention != "TEAM":
            continue
        domain = str(snapshot.get("domain_code") or (card.domain_code if card else "OTHER"))
        event_type = str(
            snapshot.get("event_type_code") or (card.event_type_code if card else "OTHER")
        )
        item_status = str(snapshot.get("status") or (card.status if card else "UNKNOWN"))
        by_domain[domain] = by_domain.get(domain, 0) + 1
        by_type[event_type] = by_type.get(event_type, 0) + 1
        status_counts[item_status] = status_counts.get(item_status, 0) + 1

    operational = session.scalars(
        select(GoWarehouseOperationalRecord).where(
            GoWarehouseOperationalRecord.occurred_on >= week_start,
            GoWarehouseOperationalRecord.occurred_on <= week_end,
        )
    ).all()
    return {
        "week_start": week_start,
        "week_end": week_end,
        "execution_cases": sum(by_domain.values()),
        "by_domain": _ranked(by_domain),
        "by_event_type": _ranked(by_type),
        "by_status": _ranked(status_counts),
        "operations": {
            "inbound_completed": sum(
                row.completed_quantity for row in operational if row.kind == "inbound"
            ),
            "return_items": sum(row.item_count for row in operational if row.kind == "returns"),
            "picked_shipments": sum(
                row.shipment_count for row in operational if row.kind == "picking"
            ),
            "picked_items": sum(row.item_count for row in operational if row.kind == "picking"),
            "consignment_packages": sum(
                row.shipment_count for row in operational if row.kind == "consignment"
            ),
        },
    }


def _weekly_response(record: WeeklyOperationsInput) -> WeeklyOperationsResponse:
    return WeeklyOperationsResponse(
        id=record.id,
        week_start=record.week_start,
        warehouse=record.warehouse,
        labor_hours=record.labor_hours,
        processing_quantity=record.processing_quantity,
        consumables_inventory_note=record.consumables_inventory_note,
        inventory_count_quantity=record.inventory_count_quantity,
        inventory_variance_quantity=record.inventory_variance_quantity,
        pallet_placement_note=record.pallet_placement_note,
    )


def _ranked(counts: dict[str, int]) -> list[dict[str, object]]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
