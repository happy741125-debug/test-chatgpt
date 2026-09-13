from __future__ import annotations

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def test_work_calendar_defaults_to_sunday_closed(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/api/admin/work-calendar", headers=OPS_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "closed_weekdays": [6],
        "holiday_dates": [],
        "working_dates": [],
        "cutoff_time": "13:00",
        "timezone": "Asia/Taipei",
    }


def test_work_calendar_can_be_updated_and_reloaded(test_context) -> None:
    client, _, _ = test_context
    payload = {
        "closed_weekdays": [6, 5, 6],
        "holiday_dates": ["2026-10-10", "2026-09-25", "2026-10-10"],
        "working_dates": ["2026-09-26"],
    }

    updated = client.patch("/api/admin/work-calendar", headers=OPS_HEADERS, json=payload)
    reloaded = client.get("/api/admin/work-calendar", headers=OPS_HEADERS)

    assert updated.status_code == 200
    assert reloaded.status_code == 200
    assert reloaded.json()["closed_weekdays"] == [5, 6]
    assert reloaded.json()["holiday_dates"] == ["2026-09-25", "2026-10-10"]
    assert reloaded.json()["working_dates"] == ["2026-09-26"]


def test_work_calendar_rejects_ambiguous_or_unusable_rules(test_context) -> None:
    client, _, _ = test_context
    all_closed = client.patch(
        "/api/admin/work-calendar",
        headers=OPS_HEADERS,
        json={"closed_weekdays": list(range(7)), "holiday_dates": [], "working_dates": []},
    )
    overlap = client.patch(
        "/api/admin/work-calendar",
        headers=OPS_HEADERS,
        json={
            "closed_weekdays": [6],
            "holiday_dates": ["2026-10-10"],
            "working_dates": ["2026-10-10"],
        },
    )

    assert all_closed.status_code == 422
    assert all_closed.json()["detail"]["error_code"] == "NO_WEEKLY_WORKDAY"
    assert overlap.status_code == 422
    assert overlap.json()["detail"]["error_code"] == "CALENDAR_DATE_CONFLICT"


def test_work_calendar_requires_admin_password(test_context) -> None:
    client, _, _ = test_context
    assert client.get("/api/admin/work-calendar").status_code == 403
    assert (
        client.patch(
            "/api/admin/work-calendar",
            json={"closed_weekdays": [6], "holiday_dates": [], "working_dates": []},
        ).status_code
        == 403
    )
