from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.models import ExecutiveMetricSnapshot

router = APIRouter(prefix="/api/dashboard/ceo", tags=["executive-dashboard"])

METRIC_DEFINITIONS = (
    {
        "code": "REVENUE",
        "label": "營收",
        "caption": "本月貨達產生的營業收入",
        "unit": "萬元",
        "direction": "HIGHER_IS_BETTER",
        "expected_source": "財務報表",
    },
    {
        "code": "GROSS_MARGIN",
        "label": "毛利率",
        "caption": "扣除直接履約成本後的獲利空間",
        "unit": "%",
        "direction": "HIGHER_IS_BETTER",
        "expected_source": "財務報表",
    },
    {
        "code": "CASH",
        "label": "現金",
        "caption": "公司目前可動用的現金水位",
        "unit": "萬元",
        "direction": "HIGHER_IS_BETTER",
        "expected_source": "銀行／財務",
    },
    {
        "code": "PEOPLE_EFFICIENCY",
        "label": "人效",
        "caption": "每人每小時完成的出貨單量",
        "unit": "單／人時",
        "direction": "HIGHER_IS_BETTER",
        "expected_source": "GOwarehouse＋人事",
    },
    {
        "code": "ORDER_EFFICIENCY",
        "label": "單效",
        "caption": "完成一張訂單所需的履約成本",
        "unit": "元／單",
        "direction": "LOWER_IS_BETTER",
        "expected_source": "GOwarehouse＋財務",
    },
    {
        "code": "SPACE_EFFICIENCY",
        "label": "坪效",
        "caption": "每坪倉儲空間產生的毛利",
        "unit": "元／坪",
        "direction": "HIGHER_IS_BETTER",
        "expected_source": "GOwarehouse＋財務",
    },
    {
        "code": "QUALITY",
        "label": "品質",
        "caption": "在承諾時間內完成出貨的比例",
        "unit": "% 準時出貨",
        "direction": "HIGHER_IS_BETTER",
        "expected_source": "GOwarehouse",
    },
)
DEFINITIONS_BY_CODE = {item["code"]: item for item in METRIC_DEFINITIONS}


class ExecutiveMetric(BaseModel):
    code: str
    label: str
    caption: str
    unit: str
    direction: str
    expected_source: str
    current_value: float | None
    target_value: float | None
    health_status: str
    period_label: str | None
    source_label: str | None
    note: str | None
    updated_at: datetime | None


class ExecutiveDashboard(BaseModel):
    metrics: list[ExecutiveMetric]
    configured: int
    total: int


class ExecutiveMetricUpdate(BaseModel):
    current_value: float | None = None
    target_value: float | None = None
    health_status: Literal["GREEN", "YELLOW", "RED", "NO_DATA"] = "NO_DATA"
    period_label: str | None = Field(default=None, max_length=80)
    source_label: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


@router.get("")
def get_executive_dashboard(
    _: OpsAccess,
    session: SessionDependency,
) -> ExecutiveDashboard:
    snapshots = {
        row.metric_code: row
        for row in session.scalars(select(ExecutiveMetricSnapshot)).all()
    }
    metrics = [
        _metric_response(definition, snapshots.get(definition["code"]))
        for definition in METRIC_DEFINITIONS
    ]
    return ExecutiveDashboard(
        metrics=metrics,
        configured=sum(metric.current_value is not None for metric in metrics),
        total=len(metrics),
    )


@router.patch("/{metric_code}")
def update_executive_metric(
    metric_code: str,
    update: ExecutiveMetricUpdate,
    _: OpsAccess,
    session: SessionDependency,
) -> ExecutiveMetric:
    code = metric_code.upper()
    definition = DEFINITIONS_BY_CODE.get(code)
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "EXECUTIVE_METRIC_NOT_FOUND"},
        )
    snapshot = session.get(ExecutiveMetricSnapshot, code)
    if snapshot is None:
        snapshot = ExecutiveMetricSnapshot(metric_code=code)
        session.add(snapshot)
    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(snapshot, field_name, value)
    session.commit()
    session.refresh(snapshot)
    return _metric_response(definition, snapshot)


def _metric_response(
    definition: dict[str, str],
    snapshot: ExecutiveMetricSnapshot | None,
) -> ExecutiveMetric:
    return ExecutiveMetric(
        **definition,
        current_value=snapshot.current_value if snapshot else None,
        target_value=snapshot.target_value if snapshot else None,
        health_status=snapshot.health_status if snapshot else "NO_DATA",
        period_label=snapshot.period_label if snapshot else None,
        source_label=snapshot.source_label if snapshot else None,
        note=snapshot.note if snapshot else None,
        updated_at=snapshot.updated_at if snapshot else None,
    )
