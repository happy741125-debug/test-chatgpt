from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import ExecutiveMetricSnapshot, OperationalImportBatch, OperationalOrderRecord
from app.operations_data.importer import parse_operational_file

router = APIRouter(prefix="/api/operations", tags=["operational-performance"])


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def import_operational_report(
    _: OpsAccess,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    filename = Path(file.filename or "operations.xlsx").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "INVALID_OPERATIONS_FILE",
                "message": "請上傳 .xlsx 或 .csv 檔案。",
            },
        )
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    existing = session.scalar(
        select(OperationalImportBatch).where(OperationalImportBatch.checksum_sha256 == checksum)
    )
    if existing is not None:
        return {
            "duplicate": True,
            "record_count": existing.record_count,
            "warning_count": existing.warning_count,
            "message": "這份營運報表已匯入過，沒有重複建立資料。",
        }
    try:
        parsed = parse_operational_file(content, suffix)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "INVALID_OPERATIONS_FILE", "message": str(exc)},
        ) from exc

    batch = OperationalImportBatch(
        checksum_sha256=checksum,
        source_filename=filename,
        record_count=len(parsed.records),
        warning_count=len(parsed.warnings),
    )
    session.add(batch)
    session.flush()
    for item in parsed.records:
        record = session.get(OperationalOrderRecord, item.order_id)
        values = item.__dict__
        if record is None:
            session.add(OperationalOrderRecord(import_batch_id=batch.id, **values))
        else:
            record.import_batch_id = batch.id
            for field, value in values.items():
                setattr(record, field, value)
    session.flush()
    _update_quality_metric(session)
    session.commit()
    return {
        "duplicate": False,
        "record_count": len(parsed.records),
        "warning_count": len(parsed.warnings),
        "warnings": list(parsed.warnings[:20]),
        "message": "營運資料已更新，原始報表未保存。",
    }


@router.get("/dashboard")
def get_operational_dashboard(_: OpsAccess, session: SessionDependency) -> dict[str, object]:
    return build_operational_dashboard(session)


@router.get("/template")
def download_operational_template(_: OpsAccess) -> Response:
    content = (
        "訂單編號,訂單日期,倉別,客戶名稱,承諾出貨時間,實際出貨時間,狀態,急單,異常數,處理分鐘,人時\n"
        "ORD-範例-001,2026-09-08,汐止,範例客戶,"
        "2026-09-09 17:00,2026-09-09 16:30,已出貨,否,0,45,0.75\n"
    )
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="huoda-operations-template.csv"'},
    )


def build_operational_dashboard(session) -> dict[str, object]:  # type: ignore[no-untyped-def]
    records = session.scalars(
        select(OperationalOrderRecord).order_by(OperationalOrderRecord.order_date)
    ).all()
    if not records:
        return {
            "has_data": False,
            "period": None,
            "kpis": {},
            "warehouses": [],
            "latest_import": None,
        }
    latest_date = max(record.order_date for record in records)
    period = latest_date.strftime("%Y-%m")
    current = [record for record in records if record.order_date.strftime("%Y-%m") == period]
    kpis = _kpis(current)
    grouped: dict[str, list[OperationalOrderRecord]] = defaultdict(list)
    for record in current:
        grouped[record.warehouse].append(record)
    warehouses = [
        {"name": name, **_kpis(items)}
        for name, items in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)
    ]
    latest_batch = session.scalar(
        select(OperationalImportBatch).order_by(OperationalImportBatch.imported_at.desc()).limit(1)
    )
    return {
        "has_data": True,
        "period": period,
        "kpis": kpis,
        "warehouses": warehouses,
        "latest_import": {
            "filename": latest_batch.source_filename,
            "record_count": latest_batch.record_count,
            "warning_count": latest_batch.warning_count,
            "imported_at": latest_batch.imported_at,
        }
        if latest_batch
        else None,
    }


def operational_review_signals(session) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    dashboard = build_operational_dashboard(session)
    if not dashboard["has_data"]:
        return []
    kpis = dashboard["kpis"]
    assert isinstance(kpis, dict)
    signals: list[dict[str, object]] = []
    on_time = kpis.get("on_time_rate")
    if isinstance(on_time, (int, float)) and on_time < 95:
        signals.append(
            {
                "code": "ON_TIME_SHIPMENT",
                "label": "準時出貨率",
                "health_status": "RED" if on_time < 90 else "YELLOW",
                "current_value": on_time,
                "target_value": 95.0,
                "unit": "%",
                "note": f"{dashboard['period']} 準時出貨率低於 95%，需確認延誤原因。",
            }
        )
    urgent_rate = float(kpis.get("urgent_rate") or 0)
    if urgent_rate >= 10:
        signals.append(
            {
                "code": "URGENT_ORDER_RATE",
                "label": "急單比例",
                "health_status": "RED" if urgent_rate >= 20 else "YELLOW",
                "current_value": urgent_rate,
                "target_value": 10.0,
                "unit": "%",
                "note": "急單比例偏高，需確認客戶需求與內部排程是否可改善。",
            }
        )
    exception_rate = float(kpis.get("exception_rate") or 0)
    if exception_rate >= 3:
        signals.append(
            {
                "code": "OPERATION_EXCEPTION_RATE",
                "label": "作業異常率",
                "health_status": "RED" if exception_rate >= 5 else "YELLOW",
                "current_value": exception_rate,
                "target_value": 3.0,
                "unit": "%",
                "note": "發生異常的訂單比例偏高，需追蹤重複原因與責任流程。",
            }
        )
    return signals


def _kpis(records: list[OperationalOrderRecord]) -> dict[str, object]:
    total = len(records)
    completed = [record for record in records if record.status == "COMPLETED"]
    timed = [record for record in completed if record.completed_at and record.promised_at]
    on_time = [
        record
        for record in timed
        if _as_utc(record.completed_at) <= _as_utc(record.promised_at)  # type: ignore[arg-type]
    ]
    processing = [record.processing_minutes for record in records if record.processing_minutes]
    worker_hours = sum(record.worker_hours or 0 for record in records)
    return {
        "total_orders": total,
        "completed_orders": len(completed),
        "completion_rate": _percent(len(completed), total),
        "on_time_rate": _percent(len(on_time), len(timed)) if timed else None,
        "urgent_rate": _percent(sum(record.urgent for record in records), total),
        "exception_rate": _percent(sum(record.exception_count > 0 for record in records), total),
        "average_processing_minutes": round(sum(processing) / len(processing), 1)
        if processing
        else None,
        "orders_per_worker_hour": round(total / worker_hours, 2) if worker_hours else None,
    }


def _update_quality_metric(session) -> None:  # type: ignore[no-untyped-def]
    dashboard = build_operational_dashboard(session)
    if not dashboard["has_data"]:
        return
    kpis = dashboard["kpis"]
    assert isinstance(kpis, dict)
    value = kpis.get("on_time_rate")
    if not isinstance(value, (int, float)):
        return
    snapshot = session.get(ExecutiveMetricSnapshot, "QUALITY")
    if snapshot is None:
        snapshot = ExecutiveMetricSnapshot(metric_code="QUALITY")
        session.add(snapshot)
    snapshot.current_value = value
    snapshot.target_value = snapshot.target_value or 95
    snapshot.health_status = "GREEN" if value >= 95 else "YELLOW" if value >= 90 else "RED"
    snapshot.period_label = str(dashboard["period"])
    snapshot.source_label = "GOwarehouse／營運報表匯入"
    snapshot.note = "依有承諾與實際出貨時間的訂單自動計算。"


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC)
