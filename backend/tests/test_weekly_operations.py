from __future__ import annotations

from datetime import date

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def test_weekly_manual_input_upserts_and_keeps_history(test_context) -> None:
    client, _, _ = test_context
    payload = {
        "week_start": "2026-09-07",
        "warehouse": "測試倉",
        "labor_hours": 35.5,
        "processing_quantity": 120,
        "consumables_inventory_note": "包材庫存正常",
        "inventory_count_quantity": 500,
        "inventory_variance_quantity": -2,
        "pallet_placement_note": "A 區剩餘 3 板位",
    }
    saved = client.put("/api/weekly-operations", headers=OPS_HEADERS, json=payload)
    assert saved.status_code == 200
    payload["labor_hours"] = 36
    updated = client.put("/api/weekly-operations", headers=OPS_HEADERS, json=payload)
    assert updated.json()["id"] == saved.json()["id"]
    assert updated.json()["labor_hours"] == 36
    history = client.get("/api/weekly-operations", headers=OPS_HEADERS).json()
    assert len(history) == 1


def test_execution_summary_has_stable_empty_shape(test_context) -> None:
    client, _, _ = test_context
    response = client.get(
        "/api/weekly-operations/execution-summary",
        headers=OPS_HEADERS,
        params={"week_start": date(2026, 9, 7).isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_cases"] == 0
    assert body["operations"]["picked_items"] == 0


def test_weekly_operations_require_admin(test_context) -> None:
    client, _, _ = test_context
    assert client.get("/api/weekly-operations").status_code == 403
