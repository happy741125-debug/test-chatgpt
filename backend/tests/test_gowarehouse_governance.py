from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GoWarehouseOrder, MerchantMaster

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}
UPLOAD_HEADERS = {"X-Upload-Token": "test-upload-token"}


def _xlsx(header: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _create_merchant(client, name: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/gw-imports/governance/merchants",
        headers=OPS_HEADERS,
        json={"name": name, "aliases": []},
    )
    assert response.status_code == 201
    return response.json()


def test_catalog_seeds_warehouses_and_blocks_arbitrary_aliases(test_context) -> None:
    client, _, _ = test_context
    catalog = client.get("/api/gw-imports/catalog", headers=UPLOAD_HEADERS)
    assert catalog.status_code == 200
    assert {item["name"] for item in catalog.json()["warehouses"]} == {"淡水倉", "汐止倉"}
    assert catalog.json()["merchants"] == []

    created = client.post(
        "/api/gw-imports/governance/merchants",
        headers=OPS_HEADERS,
        json={"name": "測試品牌", "code": "OWNER-01", "aliases": ["測試牌"]},
    )
    assert created.status_code == 201
    conflict = client.post(
        "/api/gw-imports/governance/merchants",
        headers=OPS_HEADERS,
        json={"name": "測試牌"},
    )
    assert conflict.status_code == 409


def test_order_preview_requires_controlled_assignments_and_can_be_undone(test_context) -> None:
    client, database, _ = test_context
    merchant = _create_merchant(client, "測試品牌")
    other_merchant = _create_merchant(client, "第二品牌")
    catalog = client.get("/api/gw-imports/catalog", headers=UPLOAD_HEADERS).json()
    warehouse = next(item for item in catalog["warehouses"] if item["name"] == "淡水倉")
    content = _xlsx(
        ["訂單編號", "品號", "通路名稱", "訂單金額"],
        [
            ["ORD-DEMO-001", "SKU-UNKNOWN", "官網", 100],
            ["ORD-DEMO-001", "SKU-OTHER", "官網", 100],
        ],
    )
    preview = client.post(
        "/api/gw-imports/preview/orders",
        headers=UPLOAD_HEADERS,
        files={"file": ("orders.xlsx", content, "application/octet-stream")},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["record_count"] == 1
    assert body["requires_merchant_selection"] is True
    assert body["requires_warehouse_selection"] is True
    assert "ORD-DEMO-001" not in preview.text

    missing = client.post(
        "/api/gw-imports/commit/orders",
        headers=UPLOAD_HEADERS,
        files={"file": ("orders.xlsx", content, "application/octet-stream")},
        data={"preview_checksum": body["preview_checksum"]},
    )
    assert missing.status_code == 422

    committed = client.post(
        "/api/gw-imports/commit/orders",
        headers=UPLOAD_HEADERS,
        files={"file": ("orders.xlsx", content, "application/octet-stream")},
        data={
            "preview_checksum": body["preview_checksum"],
            "merchant_id": merchant["id"],
            "warehouse_id": warehouse["id"],
        },
    )
    assert committed.status_code == 201
    batch_id = committed.json()["batch_id"]
    duplicate = client.post(
        "/api/gw-imports/commit/orders",
        headers=UPLOAD_HEADERS,
        files={"file": ("orders.xlsx", content, "application/octet-stream")},
        data={
            "preview_checksum": body["preview_checksum"],
            "merchant_id": merchant["id"],
            "warehouse_id": warehouse["id"],
        },
    )
    assert duplicate.json()["duplicate"] is True

    corrected = client.patch(
        f"/api/gw-imports/governance/batches/{batch_id}",
        headers=OPS_HEADERS,
        json={"merchant_id": other_merchant["id"]},
    )
    assert corrected.status_code == 200
    with Session(database.engine) as session:
        order = session.scalar(select(GoWarehouseOrder))
        assert order is not None
        assert order.merchant == "第二品牌"
        assert order.warehouse == "淡水倉"

    wrong_confirm = client.post(
        f"/api/gw-imports/governance/batches/{batch_id}/undo",
        headers=OPS_HEADERS,
        json={"confirm": "wrong"},
    )
    assert wrong_confirm.status_code == 400
    undone = client.post(
        f"/api/gw-imports/governance/batches/{batch_id}/undo",
        headers=OPS_HEADERS,
        json={"confirm": batch_id},
    )
    assert undone.status_code == 200
    with Session(database.engine) as session:
        assert session.scalar(select(GoWarehouseOrder)) is None


def test_inventory_auto_adds_source_merchant_as_pending(test_context) -> None:
    client, database, _ = test_context
    catalog = client.get("/api/gw-imports/catalog", headers=UPLOAD_HEADERS).json()
    warehouse = next(item for item in catalog["warehouses"] if item["name"] == "汐止倉")
    content = _xlsx(
        ["貨主名稱", "品號", "商品名稱", "數量"],
        [["匯出檔新品牌", "SKU-DEMO", "測試商品", 10]],
    )
    preview = client.post(
        "/api/gw-imports/preview/inventory",
        headers=UPLOAD_HEADERS,
        files={"file": ("inventory.xlsx", content, "application/octet-stream")},
    ).json()
    assert preview["requires_merchant_selection"] is False
    assert preview["requires_warehouse_selection"] is True
    committed = client.post(
        "/api/gw-imports/commit/inventory",
        headers=UPLOAD_HEADERS,
        files={"file": ("inventory.xlsx", content, "application/octet-stream")},
        data={
            "preview_checksum": preview["preview_checksum"],
            "warehouse_id": warehouse["id"],
        },
    )
    assert committed.status_code == 201
    with Session(database.engine) as session:
        merchant = session.scalar(
            select(MerchantMaster).where(MerchantMaster.name == "匯出檔新品牌")
        )
        assert merchant is not None
        assert merchant.status == "PENDING"


def test_picking_detects_source_merchant_and_warehouse_without_manual_input(
    test_context,
) -> None:
    client, _, _ = test_context
    content = _xlsx(
        ["揀貨單編號", "貨主", "倉庫", "出貨單數", "總件數"],
        [["PICK-DEMO-01", "來源品牌", "未來新倉", 2, 8]],
    )
    preview = client.post(
        "/api/gw-imports/preview/picking",
        headers=UPLOAD_HEADERS,
        files={"file": ("picking.xlsx", content, "application/octet-stream")},
    ).json()
    assert preview["requires_merchant_selection"] is False
    assert preview["requires_warehouse_selection"] is False
    response = client.post(
        "/api/gw-imports/commit/picking",
        headers=UPLOAD_HEADERS,
        files={"file": ("picking.xlsx", content, "application/octet-stream")},
        data={"preview_checksum": preview["preview_checksum"]},
    )
    assert response.status_code == 201


def test_cleanup_duplicate_orders_is_dry_run_then_recoverable(test_context) -> None:
    client, database, _ = test_context
    content = _xlsx(["訂單編號"], [["ORD-DUPLICATE"]])
    for merchant in ("錯誤名稱", "正確名稱"):
        response = client.post(
            "/api/gw-imports/orders",
            headers=OPS_HEADERS,
            files={"file": ("orders.xlsx", content, "application/octet-stream")},
            data={"merchant": merchant},
        )
        assert response.status_code == 201
    dry_run = client.post(
        "/api/gw-imports/governance/cleanup-orders",
        headers=OPS_HEADERS,
        json={"confirm": ""},
    )
    assert dry_run.json() == {"dry_run": True, "duplicate_records": 1}
    cleaned = client.post(
        "/api/gw-imports/governance/cleanup-orders",
        headers=OPS_HEADERS,
        json={"confirm": "MERGE-DUPLICATE-ORDERS"},
    ).json()
    assert cleaned["duplicate_records"] == 1
    with Session(database.engine) as session:
        assert len(session.scalars(select(GoWarehouseOrder)).all()) == 1
    undo = client.post(
        f"/api/gw-imports/governance/batches/{cleaned['batch_id']}/undo",
        headers=OPS_HEADERS,
        json={"confirm": cleaned["batch_id"]},
    )
    assert undo.status_code == 200
    with Session(database.engine) as session:
        assert len(session.scalars(select(GoWarehouseOrder)).all()) == 2
