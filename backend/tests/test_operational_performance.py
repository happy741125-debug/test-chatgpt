from __future__ import annotations

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _operations_csv() -> bytes:
    return (
        "訂單編號,訂單日期,倉別,客戶名稱,承諾出貨時間,實際出貨時間,狀態,急單,異常數,處理分鐘,人時\n"
        "ORD-001,2026-09-01,汐止,A客戶,2026-09-02 17:00,2026-09-02 16:00,已出貨,否,0,60,1\n"
        "ORD-002,2026-09-02,汐止,B客戶,2026-09-03 17:00,2026-09-03 18:00,已出貨,是,1,90,1.5\n"
        "ORD-003,2026-09-03,淡水,C客戶,2026-09-04 17:00,2026-09-04 16:30,已出貨,是,0,45,0.5\n"
        "ORD-004,2026-09-04,淡水,D客戶,2026-09-05 17:00,,處理中,否,1,30,0.5\n"
    ).encode("utf-8-sig")


def test_operational_import_builds_kpis_and_review_signals(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    content = _operations_csv()

    imported = client.post(
        "/api/operations/imports",
        headers=OPS_HEADERS,
        files={"file": ("operations.csv", content, "text/csv")},
    )

    assert imported.status_code == 201
    assert imported.json()["record_count"] == 4
    dashboard = client.get("/api/operations/dashboard", headers=OPS_HEADERS).json()
    assert dashboard["has_data"] is True
    assert dashboard["period"] == "2026-09"
    assert dashboard["kpis"]["total_orders"] == 4
    assert dashboard["kpis"]["completion_rate"] == 75.0
    assert dashboard["kpis"]["on_time_rate"] == 66.7
    assert dashboard["kpis"]["urgent_rate"] == 50.0
    assert dashboard["kpis"]["exception_rate"] == 50.0
    assert {item["name"] for item in dashboard["warehouses"]} == {"汐止", "淡水"}

    executive = client.get("/api/dashboard/ceo", headers=OPS_HEADERS).json()
    quality = next(item for item in executive["metrics"] if item["code"] == "QUALITY")
    assert quality["current_value"] == 66.7
    assert quality["health_status"] == "RED"

    weekly = client.get("/api/weekly-reviews/current", headers=OPS_HEADERS).json()
    assert {signal["code"] for signal in weekly["metric_signals"]} >= {
        "ON_TIME_SHIPMENT",
        "URGENT_ORDER_RATE",
        "OPERATION_EXCEPTION_RATE",
    }


def test_operational_import_is_idempotent_and_template_is_available(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    content = _operations_csv()
    files = {"file": ("operations.csv", content, "text/csv")}

    first = client.post("/api/operations/imports", headers=OPS_HEADERS, files=files)
    second = client.post("/api/operations/imports", headers=OPS_HEADERS, files=files)
    template = client.get("/api/operations/template", headers=OPS_HEADERS)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["duplicate"] is True
    assert template.status_code == 200
    assert "訂單編號" in template.content.decode("utf-8-sig")
