from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from sqlalchemy.orm import Session

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}
UPLOAD_HEADERS = {"X-Upload-Token": "test-upload-token"}


def _xlsx(header: list[str], rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


ORDER_HEADER = [
    "訂單編號",
    "通路名稱",
    "電商平台",
    "物流類型",
    "訂單金額",
    "急單",
    "預約出貨日",
    "出貨時間",
    "訂單狀態",
    "建立時間",
]


def _orders_xlsx() -> bytes:
    return _xlsx(
        ORDER_HEADER,
        [
            # on-time urgent order (shipped on/before reserved date)
            ["ORD-001", "蝦皮", "蝦皮", "宅配", 680, "Y", "2026-09-10", "2026-09-10 12:00:00",
             "已完成", "2026-09-08 08:54:33"],
            # same order id again as a second line item -> must dedupe
            ["ORD-001", "蝦皮", "蝦皮", "宅配", 680, "Y", "2026-09-10", "2026-09-10 12:00:00",
             "已完成", "2026-09-08 08:54:33"],
            # late order
            ["ORD-002", "官網", "", "新竹物流", 1200, "N", "2026-09-10", "2026-09-12 09:00:00",
             "已完成", "2026-09-08 09:03:33"],
        ],
    )


INVENTORY_HEADER = [
    "貨主名稱",
    "品號",
    "商品名稱",
    "庫存類型",
    "數量",
    "批號",
    "效期",
    "狀態",
    "可用數量",
    "已分配數量",
]


def _inventory_xlsx(near_expiry: str) -> bytes:
    return _xlsx(
        INVENTORY_HEADER,
        [
            [
                "1001｜測試品牌A",
                "SKU-A",
                "測試商品A",
                "良品",
                695,
                "",
                "2027-06-21",
                "有庫存",
                487,
                77,
            ],
            ["1002｜測試品牌B", "SKU-B", "測試商品B", "瑕疵品", 1, "", near_expiry, "有庫存", 1, 0],
        ],
    )


def test_import_orders_dedupes_and_requires_merchant(test_context) -> None:
    client, _, _ = test_context
    content = _orders_xlsx()

    # missing merchant -> 422
    missing = client.post(
        "/api/gw-imports/orders",
        headers=OPS_HEADERS,
        files={"file": ("orders.xlsx", content, "application/octet-stream")},
        data={"merchant": "  "},
    )
    assert missing.status_code == 422

    ok = client.post(
        "/api/gw-imports/orders",
        headers=OPS_HEADERS,
        files={"file": ("orders.xlsx", content, "application/octet-stream")},
        data={"merchant": "測試品牌A"},
    )
    assert ok.status_code == 201
    assert ok.json()["record_count"] == 2  # ORD-001 deduped

    # duplicate upload of the same file+merchant is detected
    dup = client.post(
        "/api/gw-imports/orders",
        headers=OPS_HEADERS,
        files={"file": ("orders.xlsx", content, "application/octet-stream")},
        data={"merchant": "測試品牌A"},
    )
    assert dup.json()["duplicate"] is True


def test_import_inventory_and_summary(test_context) -> None:
    client, _, _ = test_context
    from datetime import UTC, datetime, timedelta

    near = (datetime.now(UTC).date() + timedelta(days=10)).isoformat()

    inv = client.post(
        "/api/gw-imports/inventory",
        headers=OPS_HEADERS,
        files={"file": ("inv.xlsx", _inventory_xlsx(near), "application/octet-stream")},
    )
    assert inv.status_code == 201
    assert inv.json()["record_count"] == 2
    assert set(inv.json()["merchants"]) == {"1001｜測試品牌A", "1002｜測試品牌B"}

    client.post(
        "/api/gw-imports/orders",
        headers=OPS_HEADERS,
        files={"file": ("orders.xlsx", _orders_xlsx(), "application/octet-stream")},
        data={"merchant": "測試品牌A"},
    )

    summary = client.get("/api/gw-imports/summary", headers=OPS_HEADERS).json()

    orders = summary["orders"]
    assert orders["has_data"] is True
    assert orders["total_orders"] == 2
    assert orders["urgent_orders"] == 1
    assert orders["urgent_rate"] == 50.0
    assert orders["revenue"] == 1880.0
    # ORD-001 on time, ORD-002 late -> 1/2
    assert orders["on_time_basis"] == 2
    assert orders["on_time_rate"] == 50.0

    inventory = summary["inventory"]
    assert inventory["has_data"] is True
    assert inventory["sku_lines"] == 2
    assert inventory["defective_lines"] == 1
    assert inventory["near_expiry_lines"] == 1
    assert inventory["total_available"] == 488


def test_summary_empty_when_nothing_imported(test_context) -> None:
    client, _, _ = test_context
    summary = client.get("/api/gw-imports/summary", headers=OPS_HEADERS).json()
    assert summary["orders"]["has_data"] is False
    assert summary["inventory"]["has_data"] is False
    assert summary["operations"]["has_data"] is False


def test_imports_require_ops_token(test_context) -> None:
    client, _, _ = test_context
    assert client.get("/api/gw-imports/summary").status_code == 403


def test_operational_exports_build_metrics_without_pii(test_context) -> None:
    client, database, _ = test_context
    files = {
        "inbound": _xlsx(
            [
                "單號", "品號", "預計入倉日期", "進倉類別", "預計入庫數量",
                "實際驗收數量", "實際上架數量", "狀態",
            ],
            [["IN-DEMO-1", "SKU-A", "2026-09-08", "收貨入庫", 20, 18, 16, "已完成"]],
        ),
        "returns": _xlsx(
            ["退貨單號", "品號", "數量", "庫存類型", "狀態", "建立時間"],
            [["RET-DEMO-1", "SKU-A", 2, "GOOD", "已完成", "2026-09-08 10:00:00"]],
        ),
        "picking": _xlsx(
            ["揀貨單編號", "倉庫", "銷售通路", "出貨單數", "總件數", "狀態", "建立時間"],
            [["PICK-DEMO-1", "測試倉", "官網", 4, 40, "已完成", "2026-09-08 12:00:00"]],
        ),
        "consignment": _xlsx(
            ["託運單號", "件數", "類別", "模式", "狀態", "配達日", "收件人", "地址", "電話"],
            [[
                "SHIP-DEMO-1", 3, "測試物流", "正物流", "已出貨", "2026-09-09",
                "不應保存", "不應保存", "0000",
            ]],
        ),
    }
    for kind, content in files.items():
        response = client.post(
            f"/api/gw-imports/{kind}",
            headers=OPS_HEADERS,
            files={"file": (f"{kind}.xlsx", content, "application/octet-stream")},
        )
        assert response.status_code == 201

    metrics = client.get("/api/gw-imports/summary", headers=OPS_HEADERS).json()["operations"]
    assert metrics == {
        "has_data": True,
        "inbound_planned": 20,
        "inbound_accepted": 18,
        "inbound_completed": 16,
        "return_items": 2,
        "picked_shipments": 4,
        "picked_items": 40,
        "return_rate": 5.0,
        "consignment_packages": 3,
        "delivery_types": [{"name": "測試物流", "packages": 3}],
        "warehouses": [{"warehouse": "測試倉", "shipments": 4, "items": 40}],
    }
    with Session(database.engine) as session:
        from app.models import GoWarehouseOperationalRecord

        records = session.query(GoWarehouseOperationalRecord).all()
        serialized = " ".join(str(record.__dict__) for record in records)
        assert "不應保存" not in serialized
        assert "SHIP-DEMO-1" not in serialized


def test_upload_token_must_use_preview_and_cannot_read_dashboard(test_context) -> None:
    client, _, _ = test_context
    direct = client.post(
        "/api/gw-imports/picking",
        headers=UPLOAD_HEADERS,
        files={
            "file": (
                "picking.xlsx",
                _xlsx(["揀貨單編號", "出貨單數", "總件數"], [["PICK-DEMO", 1, 3]]),
                "application/octet-stream",
            )
        },
    )
    assert direct.status_code == 403
    preview = client.post(
        "/api/gw-imports/preview/picking",
        headers=UPLOAD_HEADERS,
        files={
            "file": (
                "picking.xlsx",
                _xlsx(
                    ["揀貨單編號", "貨主", "倉庫", "出貨單數", "總件數"],
                    [["PICK-DEMO", "測試貨主", "測試倉", 1, 3]],
                ),
                "application/octet-stream",
            )
        },
    )
    assert preview.status_code == 200
    assert client.get("/api/gw-imports/summary", headers=UPLOAD_HEADERS).status_code == 403
