from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


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
            ["1042｜日日好食", "SKU-A", "拌麵", "良品", 695, "", "2027-06-21", "有庫存", 487, 77],
            ["1051｜度小月", "SKU-B", "醬油", "瑕疵品", 1, "", near_expiry, "有庫存", 1, 0],
        ],
    )


def test_import_orders_dedupes_and_requires_merchant(test_context) -> None:
    client, _, _ = test_context

    # missing merchant -> 422
    missing = client.post(
        "/api/gw-imports/orders",
        headers=OPS_HEADERS,
        files={"file": ("orders.xlsx", _orders_xlsx(), "application/octet-stream")},
        data={"merchant": "  "},
    )
    assert missing.status_code == 422

    ok = client.post(
        "/api/gw-imports/orders",
        headers=OPS_HEADERS,
        files={"file": ("orders.xlsx", _orders_xlsx(), "application/octet-stream")},
        data={"merchant": "日日好食"},
    )
    assert ok.status_code == 201
    assert ok.json()["record_count"] == 2  # ORD-001 deduped

    # duplicate upload of the same file+merchant is detected
    dup = client.post(
        "/api/gw-imports/orders",
        headers=OPS_HEADERS,
        files={"file": ("orders.xlsx", _orders_xlsx(), "application/octet-stream")},
        data={"merchant": "日日好食"},
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
    assert set(inv.json()["merchants"]) == {"1042｜日日好食", "1051｜度小月"}

    client.post(
        "/api/gw-imports/orders",
        headers=OPS_HEADERS,
        files={"file": ("orders.xlsx", _orders_xlsx(), "application/octet-stream")},
        data={"merchant": "日日好食"},
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


def test_imports_require_ops_token(test_context) -> None:
    client, _, _ = test_context
    assert client.get("/api/gw-imports/summary").status_code == 403
