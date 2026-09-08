from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import (
    ExecutiveMetricSnapshot,
    RevenueDataIssue,
    RevenueImportBatch,
    RevenueRecord,
)
from app.revenue.importer import ParsedRevenueWorkbook, parse_revenue_workbook

router = APIRouter(prefix="/api/revenue", tags=["revenue"])
CATEGORY_LABELS = {
    "warehouse_rent": "倉租",
    "handling_system": "理貨／系統",
    "processing": "加工",
    "logistics": "物流",
    "other": "其他／耗材",
}


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def import_revenue_workbook(
    _: OpsAccess,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    filename = Path(file.filename or "revenue.xlsx").name
    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "INVALID_REVENUE_FILE", "message": "請上傳 .xlsx 檔案。"},
        )
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    existing = session.scalar(
        select(RevenueImportBatch).where(RevenueImportBatch.checksum_sha256 == checksum)
    )
    if existing is not None:
        return {
            "duplicate": True,
            "period_count": existing.period_count,
            "record_count": existing.record_count,
            "warning_count": existing.warning_count,
            "latest_period": _latest_period(session),
            "message": "這份 Excel 已匯入過，資料沒有重複建立。",
        }

    try:
        parsed = parse_revenue_workbook(content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "INVALID_REVENUE_FILE", "message": str(exc)},
        ) from exc

    batch = RevenueImportBatch(
        checksum_sha256=checksum,
        source_filename=filename,
        period_count=len(parsed.periods),
        record_count=len(parsed.records),
        warning_count=len(parsed.issues),
    )
    session.add(batch)
    session.flush()

    session.execute(delete(RevenueRecord).where(RevenueRecord.period.in_(parsed.periods)))
    for record in parsed.records:
        session.add(RevenueRecord(import_batch_id=batch.id, **record.__dict__))
    for issue in parsed.issues:
        session.add(RevenueDataIssue(import_batch_id=batch.id, **issue.__dict__))

    _update_revenue_metric(session, parsed)
    session.commit()
    return {
        "duplicate": False,
        "period_count": len(parsed.periods),
        "record_count": len(parsed.records),
        "warning_count": len(parsed.issues),
        "latest_period": parsed.periods[-1],
        "message": "營收資料已更新，原始 Excel 未保存。",
    }


@router.get("/dashboard")
def get_revenue_dashboard(
    _: OpsAccess,
    session: SessionDependency,
) -> dict[str, object]:
    return build_revenue_dashboard(session)


def build_revenue_dashboard(session) -> dict[str, object]:  # type: ignore[no-untyped-def]
    records = session.scalars(
        select(RevenueRecord).order_by(RevenueRecord.period, RevenueRecord.customer_name)
    ).all()
    if not records:
        return {
            "has_data": False,
            "current": None,
            "months": [],
            "warehouses": [],
            "categories": [],
            "concentration": None,
            "top_customers": [],
            "growth_alerts": [],
            "decline_alerts": [],
            "issues": [],
            "latest_import": None,
        }

    monthly_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    monthly_customer: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    customer_names: dict[str, str] = {}
    for record in records:
        amount = Decimal(record.total)
        monthly_totals[record.period] += amount
        identity = record.customer_code or record.customer_name.casefold()
        key = f"{record.warehouse}|{identity}"
        monthly_customer[record.period][key] += amount
        customer_names[key] = record.customer_name

    periods = sorted(monthly_totals)
    current_period = periods[-1]
    current_total = monthly_totals[current_period]
    previous_total = monthly_totals.get(_previous_period(current_period))
    mom_pct = _pct_change(current_total, previous_total)

    current_year, current_month = (int(part) for part in current_period.split("-"))
    ytd_total = sum(
        (
            value
            for period, value in monthly_totals.items()
            if period.startswith(f"{current_year}-")
        ),
        Decimal("0"),
    )
    prior_ytd = sum(
        (
            value
            for period, value in monthly_totals.items()
            if period.startswith(f"{current_year - 1}-") and int(period[-2:]) <= current_month
        ),
        Decimal("0"),
    )
    ytd_pct = _pct_change(ytd_total, prior_ytd if prior_ytd else None)

    current_records = [record for record in records if record.period == current_period]
    warehouses = _ranked_breakdown(current_records, "warehouse", current_total)
    categories = []
    for code, label in CATEGORY_LABELS.items():
        amount = sum((Decimal(getattr(record, code)) for record in current_records), Decimal("0"))
        if amount == 0 and code == "other":
            continue
        categories.append(
            {
                "code": code,
                "label": label,
                "amount": float(amount),
                "share_pct": _share(amount, current_total),
            }
        )

    current_customers = sorted(
        monthly_customer[current_period].items(), key=lambda item: item[1], reverse=True
    )
    top_customers = [
        {
            "name": customer_names[key],
            "amount": float(amount),
            "share_pct": _share(amount, current_total),
        }
        for key, amount in current_customers[:5]
    ]
    top2 = sum((amount for _, amount in current_customers[:2]), Decimal("0"))
    top5 = sum((amount for _, amount in current_customers[:5]), Decimal("0"))
    growth_alerts, decline_alerts = _customer_alerts(
        periods, monthly_customer, customer_names
    )

    latest_batch = session.scalar(
        select(RevenueImportBatch).order_by(RevenueImportBatch.imported_at.desc()).limit(1)
    )
    issue_rows = []
    if latest_batch is not None:
        issue_rows = session.scalars(
            select(RevenueDataIssue)
            .where(RevenueDataIssue.import_batch_id == latest_batch.id)
            .order_by(RevenueDataIssue.period.desc(), RevenueDataIssue.severity)
        ).all()

    return {
        "has_data": True,
        "current": {
            "period": current_period,
            "total": float(current_total),
            "mom_pct": mom_pct,
            "ytd_total": float(ytd_total),
            "ytd_pct": ytd_pct,
        },
        "months": [
            {"period": period, "total": float(monthly_totals[period])}
            for period in periods[-35:]
        ],
        "warehouses": warehouses,
        "categories": categories,
        "concentration": {
            "top2_pct": _share(top2, current_total),
            "top5_pct": _share(top5, current_total),
            "risk_level": "RED"
            if _share(top2, current_total) >= 60 or _share(top5, current_total) >= 80
            else "YELLOW"
            if _share(top2, current_total) >= 50 or _share(top5, current_total) >= 75
            else "GREEN",
        },
        "top_customers": top_customers,
        "growth_alerts": growth_alerts,
        "decline_alerts": decline_alerts,
        "issues": [
            {
                "period": issue.period,
                "severity": issue.severity,
                "code": issue.code,
                "cell_reference": issue.cell_reference,
                "message": issue.message,
                "source_value": _float_or_none(issue.source_value),
                "calculated_value": _float_or_none(issue.calculated_value),
                "difference": _float_or_none(issue.difference),
            }
            for issue in issue_rows
        ],
        "latest_import": {
            "filename": latest_batch.source_filename,
            "imported_at": latest_batch.imported_at,
            "period_count": latest_batch.period_count,
            "record_count": latest_batch.record_count,
            "warning_count": latest_batch.warning_count,
        }
        if latest_batch
        else None,
    }


def revenue_review_signals(session) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    dashboard = build_revenue_dashboard(session)
    if not dashboard["has_data"]:
        return []
    signals: list[dict[str, object]] = []
    concentration = dashboard["concentration"]
    assert isinstance(concentration, dict)
    if concentration["risk_level"] in {"YELLOW", "RED"}:
        signals.append(
            {
                "code": "REVENUE_CONCENTRATION",
                "label": "大客戶營收集中",
                "health_status": concentration["risk_level"],
                "current_value": concentration["top2_pct"],
                "target_value": 50.0,
                "unit": "%（前兩大）",
                "note": f"前五大客戶占 {concentration['top5_pct']:.1f}%，需確認留客與備援計畫。",
            }
        )
    declines = dashboard["decline_alerts"]
    assert isinstance(declines, list)
    if declines:
        worst = declines[0]
        signals.append(
            {
                "code": "CUSTOMER_REVENUE_DECLINE",
                "label": "客戶營收重大下降",
                "health_status": "RED"
                if worst["change_pct"] <= -30 and worst["change_amount"] <= -50000
                else "YELLOW",
                "current_value": worst["change_pct"],
                "target_value": -15.0,
                "unit": "%（近三月）",
                "note": f"{worst['name']} 近三月較前期減少 {abs(worst['change_amount']):,.0f} 元。",
            }
        )
    return signals


def _update_revenue_metric(session, parsed: ParsedRevenueWorkbook) -> None:  # type: ignore[no-untyped-def]
    latest_period = parsed.periods[-1]
    latest_total = sum(
        (record.total for record in parsed.records if record.period == latest_period),
        Decimal("0"),
    )
    snapshot = session.get(ExecutiveMetricSnapshot, "REVENUE")
    if snapshot is None:
        snapshot = ExecutiveMetricSnapshot(metric_code="REVENUE")
        session.add(snapshot)
    snapshot.current_value = float(latest_total / Decimal("10000"))
    snapshot.period_label = latest_period
    snapshot.source_label = "營收數據表匯入"
    snapshot.note = "由客戶明細重新加總；原始 Excel 未保存。"
    if snapshot.health_status == "NO_DATA":
        snapshot.health_status = "GREEN"


def _ranked_breakdown(records, field: str, total: Decimal) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    amounts: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for record in records:
        amounts[str(getattr(record, field))] += Decimal(record.total)
    return [
        {"name": name, "amount": float(amount), "share_pct": _share(amount, total)}
        for name, amount in sorted(amounts.items(), key=lambda item: item[1], reverse=True)
    ]


def _customer_alerts(
    periods: list[str],
    monthly_customer: dict[str, dict[str, Decimal]],
    customer_names: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if len(periods) < 6:
        return [], []
    recent_periods = periods[-3:]
    prior_periods = periods[-6:-3]
    keys = set().union(*(monthly_customer[period].keys() for period in periods[-6:]))
    growth: list[dict[str, object]] = []
    decline: list[dict[str, object]] = []
    for key in keys:
        recent = sum(
            (monthly_customer[period].get(key, Decimal("0")) for period in recent_periods),
            Decimal("0"),
        )
        prior = sum(
            (monthly_customer[period].get(key, Decimal("0")) for period in prior_periods),
            Decimal("0"),
        )
        change = recent - prior
        if prior == 0:
            if recent >= Decimal("10000"):
                growth.append(
                    {
                        "name": customer_names[key],
                        "change_pct": None,
                        "change_amount": float(change),
                        "recent_total": float(recent),
                        "status": "NEW",
                    }
                )
            continue
        change_pct = float(change / prior * 100)
        item = {
            "name": customer_names[key],
            "change_pct": round(change_pct, 1),
            "change_amount": float(change),
            "recent_total": float(recent),
            "status": "GROWTH" if change > 0 else "DECLINE",
        }
        if change_pct >= 20 and change >= Decimal("10000"):
            growth.append(item)
        if change_pct <= -15 and change <= Decimal("-10000"):
            decline.append(item)
    growth.sort(key=lambda item: item["change_amount"], reverse=True)
    decline.sort(key=lambda item: item["change_amount"])
    return growth[:5], decline[:5]


def _previous_period(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _latest_period(session) -> str | None:  # type: ignore[no-untyped-def]
    row = session.scalar(
        select(RevenueRecord.period).order_by(RevenueRecord.period.desc()).limit(1)
    )
    return row


def _pct_change(current: Decimal, previous: Decimal | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return round(float((current - previous) / previous * 100), 1)


def _share(amount: Decimal, total: Decimal) -> float:
    if total == 0:
        return 0.0
    return round(float(amount / total * 100), 1)


def _float_or_none(value: object) -> float | None:
    return float(value) if value is not None else None
