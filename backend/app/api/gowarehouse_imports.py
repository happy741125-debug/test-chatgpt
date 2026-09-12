from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.gowarehouse.importer import parse_inventory_file, parse_operational_file, parse_orders_file
from app.models import (
    GoWarehouseImportBatch,
    GoWarehouseInventory,
    GoWarehouseOperationalRecord,
    GoWarehouseOrder,
)

router = APIRouter(prefix="/api/gw-imports", tags=["gowarehouse-imports"])

_NEAR_EXPIRY_DAYS = 30
_DEFECTIVE_HINTS = ("瑕疵", "不良", "defect")
_ORDER_CUTOFF = time(hour=13)
_TAIPEI = ZoneInfo("Asia/Taipei")


def _read(file: UploadFile) -> tuple[bytes, str, str]:
    filename = Path(file.filename or "export.xlsx").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "INVALID_FILE", "message": "請上傳 .xlsx 或 .csv 檔案。"},
        )
    return filename, suffix


def _duplicate_batch(session, checksum: str):  # type: ignore[no-untyped-def]
    return session.scalar(
        select(GoWarehouseImportBatch).where(
            GoWarehouseImportBatch.checksum_sha256 == checksum
        )
    )


@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def import_orders(
    _: OpsAccess,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
    merchant: Annotated[str, Form()],
) -> dict[str, object]:
    merchant = merchant.strip()
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "MERCHANT_REQUIRED", "message": "請選擇這份訂單屬於哪個品牌。"},
        )
    filename, suffix = _read(file)
    content = await file.read()
    checksum = hashlib.sha256(content + merchant.encode()).hexdigest()
    if (existing := _duplicate_batch(session, checksum)) is not None:
        return _duplicate_response(existing)
    try:
        parsed = parse_orders_file(content, suffix)
    except ValueError as exc:
        raise _invalid(exc) from exc

    batch = GoWarehouseImportBatch(
        checksum_sha256=checksum,
        source_filename=filename,
        kind="orders",
        merchant=merchant,
        record_count=len(parsed.orders),
        warning_count=len(parsed.warnings),
    )
    session.add(batch)
    session.flush()
    for item in parsed.orders:
        pk = f"{merchant}::{item.order_id}"
        record = session.get(GoWarehouseOrder, pk)
        values = {
            "import_batch_id": batch.id,
            "merchant": merchant,
            "order_id": item.order_id,
            "channel": item.channel,
            "platform": item.platform,
            "shipping_type": item.shipping_type,
            "amount": item.amount,
            "urgent": item.urgent,
            "reserved_ship_date": item.reserved_ship_date,
            "shipped_at": item.shipped_at,
            "order_status": item.order_status,
            "source_created_at": item.source_created_at,
        }
        if record is None:
            session.add(GoWarehouseOrder(id=pk, **values))
        else:
            for field, value in values.items():
                setattr(record, field, value)
    session.commit()
    return {
        "duplicate": False,
        "kind": "orders",
        "merchant": merchant,
        "record_count": len(parsed.orders),
        "message": f"已匯入 {merchant} 的 {len(parsed.orders)} 筆訂單。",
    }


@router.post("/inventory", status_code=status.HTTP_201_CREATED)
async def import_inventory(
    _: OpsAccess,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    filename, suffix = _read(file)
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    if (existing := _duplicate_batch(session, checksum)) is not None:
        return _duplicate_response(existing)
    try:
        parsed = parse_inventory_file(content, suffix)
    except ValueError as exc:
        raise _invalid(exc) from exc

    batch = GoWarehouseImportBatch(
        checksum_sha256=checksum,
        source_filename=filename,
        kind="inventory",
        merchant=None,
        record_count=len(parsed.inventory),
        warning_count=len(parsed.warnings),
    )
    session.add(batch)
    session.flush()
    for item in parsed.inventory:
        key = "|".join([item.merchant, item.sku, item.batch or "", item.inventory_type or ""])
        pk = hashlib.sha256(key.encode()).hexdigest()
        record = session.get(GoWarehouseInventory, pk)
        values = {
            "import_batch_id": batch.id,
            "merchant": item.merchant,
            "sku": item.sku,
            "product_name": item.product_name,
            "inventory_type": item.inventory_type,
            "quantity": item.quantity,
            "batch": item.batch,
            "expiration_date": item.expiration_date,
            "status": item.status,
            "available": item.available,
            "allocated": item.allocated,
        }
        if record is None:
            session.add(GoWarehouseInventory(id=pk, **values))
        else:
            for field, value in values.items():
                setattr(record, field, value)
    session.commit()
    merchants = sorted({item.merchant for item in parsed.inventory})
    return {
        "duplicate": False,
        "kind": "inventory",
        "record_count": len(parsed.inventory),
        "merchants": merchants,
        "message": f"已匯入 {len(parsed.inventory)} 筆庫存（{len(merchants)} 個品牌）。",
    }


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
async def import_operational(
    kind: str,
    _: OpsAccess,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    if kind not in {"inbound", "returns", "picking", "consignment"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="不支援的匯入類型。")
    filename, suffix = _read(file)
    content = await file.read()
    checksum = hashlib.sha256(content + kind.encode()).hexdigest()
    if (existing := _duplicate_batch(session, checksum)) is not None:
        return _duplicate_response(existing)
    try:
        parsed = parse_operational_file(content, suffix, kind)
    except ValueError as exc:
        raise _invalid(exc) from exc

    batch = GoWarehouseImportBatch(
        checksum_sha256=checksum,
        source_filename=filename,
        kind=kind,
        merchant=None,
        record_count=len(parsed.operational),
        warning_count=len(parsed.warnings),
    )
    session.add(batch)
    session.flush()
    for item in parsed.operational:
        pk = hashlib.sha256(f"{kind}|{item.source_key}".encode()).hexdigest()
        record = session.get(GoWarehouseOperationalRecord, pk)
        values = {
            "import_batch_id": batch.id,
            "kind": kind,
            "occurred_on": item.occurred_on,
            "category": item.category,
            "warehouse": item.warehouse,
            "channel": item.channel,
            "status": item.status,
            "planned_quantity": item.planned_quantity,
            "accepted_quantity": item.accepted_quantity,
            "completed_quantity": item.completed_quantity,
            "shipment_count": item.shipment_count,
            "item_count": item.item_count,
        }
        if record is None:
            session.add(GoWarehouseOperationalRecord(id=pk, **values))
        else:
            for field, value in values.items():
                setattr(record, field, value)
    session.commit()
    labels = {
        "inbound": "進倉",
        "returns": "退貨",
        "picking": "揀貨",
        "consignment": "托運",
    }
    return {
        "duplicate": False,
        "kind": kind,
        "record_count": len(parsed.operational),
        "message": f"已匯入 {len(parsed.operational)} 筆{labels[kind]}資料。",
    }


@router.get("/summary")
def import_summary(_: OpsAccess, session: SessionDependency) -> dict[str, object]:
    return {
        "orders": _orders_summary(session),
        "inventory": _inventory_summary(session),
        "operations": _operational_summary(session),
    }


def _orders_summary(session) -> dict[str, object]:  # type: ignore[no-untyped-def]
    orders = session.scalars(select(GoWarehouseOrder)).all()
    if not orders:
        return {"has_data": False}
    latest_batch = session.scalar(
        select(GoWarehouseImportBatch)
        .where(GoWarehouseImportBatch.kind == "orders")
        .order_by(GoWarehouseImportBatch.imported_at.desc())
        .limit(1)
    )
    total = len(orders)
    urgent = sum(1 for o in orders if o.urgent)
    revenue = round(sum(o.amount or 0 for o in orders), 2)
    timed = [o for o in orders if o.shipped_at and o.reserved_ship_date]
    on_time = [o for o in timed if o.shipped_at.date() <= o.reserved_ship_date]
    by_merchant: dict[str, int] = defaultdict(int)
    for o in orders:
        by_merchant[o.merchant] += 1
    scheduled_orders = [
        (order, processing_date)
        for order in orders
        if not _order_is_cancelled(order)
        and (processing_date := _order_processing_date(order)) is not None
    ]
    week_starts = {
        _week_bounds(processing_date)[0]
        for _, processing_date in scheduled_orders
    }
    current_week_start, _ = _week_bounds(datetime.now(_TAIPEI).date())
    selected_week_start = (
        None
        if not week_starts
        else (
            current_week_start
            if current_week_start in week_starts
            else max(
                (week_start for week_start in week_starts if week_start <= current_week_start),
                default=min(week_starts),
            )
        )
    )
    selected_week_end = (
        selected_week_start + timedelta(days=6) if selected_week_start else None
    )
    weekly = [
        order
        for order, processing_date in scheduled_orders
        if selected_week_start is not None
        and selected_week_end is not None
        and selected_week_start <= processing_date <= selected_week_end
    ]
    weekly_completed = [order for order in weekly if _order_is_completed(order)]
    cancelled_in_week = [
        order
        for order in orders
        if _order_is_cancelled(order)
        and (processing_date := _order_processing_date(order)) is not None
        and selected_week_start is not None
        and selected_week_end is not None
        and selected_week_start <= processing_date <= selected_week_end
    ]
    return {
        "has_data": True,
        "total_orders": total,
        "urgent_orders": urgent,
        "urgent_rate": _percent(urgent, total),
        "revenue": revenue,
        "on_time_rate": _percent(len(on_time), len(timed)) if timed else None,
        "on_time_basis": len(timed),
        "weekly_tracking_available": selected_week_start is not None,
        "week_start": selected_week_start.isoformat() if selected_week_start else None,
        "week_end": selected_week_end.isoformat() if selected_week_end else None,
        "cutoff_time": _ORDER_CUTOFF.strftime("%H:%M"),
        "completion_standard": "已完成",
        "data_updated_at": (
            latest_batch.imported_at.isoformat() if latest_batch is not None else None
        ),
        "weekly_orders": len(weekly),
        "weekly_completed_orders": len(weekly_completed),
        "weekly_pending_orders": len(weekly) - len(weekly_completed),
        "weekly_cancelled_orders": len(cancelled_in_week),
        "weekly_completion_rate": (
            _percent(len(weekly_completed), len(weekly)) if weekly else None
        ),
        "by_merchant": [
            {"merchant": name, "orders": count}
            for name, count in sorted(by_merchant.items(), key=lambda kv: kv[1], reverse=True)
        ],
    }


def _order_processing_date(order: GoWarehouseOrder) -> date | None:
    if order.reserved_ship_date:
        return order.reserved_ship_date
    if order.source_created_at:
        processing_date = order.source_created_at.date()
        if order.source_created_at.time() >= _ORDER_CUTOFF:
            processing_date += timedelta(days=1)
        return processing_date
    return None


def _order_is_completed(order: GoWarehouseOrder) -> bool:
    return (order.order_status or "").strip() == "已完成"


def _order_is_cancelled(order: GoWarehouseOrder) -> bool:
    return (order.order_status or "").strip() == "已取消"


def _week_bounds(day: date) -> tuple[date, date]:
    week_start = day - timedelta(days=day.weekday())
    return week_start, week_start + timedelta(days=6)


def _inventory_summary(session) -> dict[str, object]:  # type: ignore[no-untyped-def]
    rows = session.scalars(select(GoWarehouseInventory)).all()
    if not rows:
        return {"has_data": False}
    today = datetime.now(UTC).date()
    soon = today + timedelta(days=_NEAR_EXPIRY_DAYS)
    defective = sum(
        1 for r in rows if r.inventory_type and any(h in r.inventory_type for h in _DEFECTIVE_HINTS)
    )
    near_expiry = sum(1 for r in rows if _is_near_expiry(r.expiration_date, today, soon))
    by_merchant: dict[str, int] = defaultdict(int)
    for r in rows:
        by_merchant[r.merchant] += r.quantity or 0
    return {
        "has_data": True,
        "sku_lines": len(rows),
        "total_quantity": sum(r.quantity or 0 for r in rows),
        "total_available": sum(r.available or 0 for r in rows),
        "total_allocated": sum(r.allocated or 0 for r in rows),
        "defective_lines": defective,
        "near_expiry_lines": near_expiry,
        "by_merchant": [
            {"merchant": name, "quantity": qty}
            for name, qty in sorted(by_merchant.items(), key=lambda kv: kv[1], reverse=True)
        ],
    }


def _is_near_expiry(exp: date | None, today: date, soon: date) -> bool:
    return exp is not None and today <= exp <= soon


def _operational_summary(session) -> dict[str, object]:  # type: ignore[no-untyped-def]
    rows = session.scalars(select(GoWarehouseOperationalRecord)).all()
    if not rows:
        return {"has_data": False}
    by_kind: dict[str, list[GoWarehouseOperationalRecord]] = defaultdict(list)
    delivery_types: dict[str, int] = defaultdict(int)
    warehouses: dict[str, dict[str, int]] = defaultdict(
        lambda: {"shipments": 0, "items": 0}
    )
    for row in rows:
        by_kind[row.kind].append(row)
        if row.kind == "consignment" and row.category:
            delivery_types[row.category] += row.shipment_count
        if row.kind == "picking" and row.warehouse:
            warehouses[row.warehouse]["shipments"] += row.shipment_count
            warehouses[row.warehouse]["items"] += row.item_count

    inbound = by_kind["inbound"]
    returns = by_kind["returns"]
    picking = by_kind["picking"]
    return_items = sum(row.item_count for row in returns if row.status != "已取消")
    picked_items = sum(row.item_count for row in picking if row.status != "已終止")
    return_rate = round(return_items / picked_items * 100, 2) if picked_items else None
    return {
        "has_data": True,
        "inbound_planned": sum(row.planned_quantity for row in inbound),
        "inbound_accepted": sum(row.accepted_quantity for row in inbound),
        "inbound_completed": sum(row.completed_quantity for row in inbound),
        "return_items": return_items,
        "picked_shipments": sum(
            row.shipment_count for row in picking if row.status != "已終止"
        ),
        "picked_items": picked_items,
        "return_rate": return_rate,
        "consignment_packages": sum(row.shipment_count for row in by_kind["consignment"]),
        "delivery_types": [
            {"name": name, "packages": count}
            for name, count in sorted(
                delivery_types.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "warehouses": [
            {"warehouse": name, **values}
            for name, values in sorted(warehouses.items())
        ],
    }


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _duplicate_response(batch: GoWarehouseImportBatch) -> dict[str, object]:
    return {
        "duplicate": True,
        "kind": batch.kind,
        "record_count": batch.record_count,
        "message": "這份檔案已匯入過，沒有重複建立資料。",
    }


def _invalid(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error_code": "INVALID_FILE", "message": str(exc)},
    )
