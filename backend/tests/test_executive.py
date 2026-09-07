from __future__ import annotations

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def test_ceo_dashboard_requires_admin_token(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    response = client.get("/api/dashboard/ceo")

    assert response.status_code == 403


def test_ceo_dashboard_starts_with_seven_honest_empty_metrics(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    response = client.get("/api/dashboard/ceo", headers=OPS_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] == 0
    assert body["total"] == 7
    assert [item["code"] for item in body["metrics"]] == [
        "REVENUE",
        "GROSS_MARGIN",
        "CASH",
        "PEOPLE_EFFICIENCY",
        "ORDER_EFFICIENCY",
        "SPACE_EFFICIENCY",
        "QUALITY",
    ]
    assert all(item["health_status"] == "NO_DATA" for item in body["metrics"])


def test_ceo_metric_update_is_persistent(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    updated = client.patch(
        "/api/dashboard/ceo/GROSS_MARGIN",
        headers={**OPS_HEADERS, "Content-Type": "application/json"},
        json={
            "current_value": 31.5,
            "target_value": 35,
            "health_status": "YELLOW",
            "period_label": "2026 年 9 月",
            "source_label": "財務試算表",
            "note": "等待月底結帳確認",
        },
    )

    assert updated.status_code == 200
    assert updated.json()["current_value"] == 31.5
    dashboard = client.get("/api/dashboard/ceo", headers=OPS_HEADERS)
    gross_margin = next(
        item for item in dashboard.json()["metrics"] if item["code"] == "GROSS_MARGIN"
    )
    assert dashboard.json()["configured"] == 1
    assert gross_margin["health_status"] == "YELLOW"
    assert gross_margin["source_label"] == "財務試算表"


def test_unknown_ceo_metric_cannot_be_created(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    response = client.patch(
        "/api/dashboard/ceo/UNKNOWN",
        headers={**OPS_HEADERS, "Content-Type": "application/json"},
        json={"current_value": 1, "health_status": "GREEN"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "EXECUTIVE_METRIC_NOT_FOUND"
