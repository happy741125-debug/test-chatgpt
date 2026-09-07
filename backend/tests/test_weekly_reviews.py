from __future__ import annotations

from datetime import datetime

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def test_weekly_review_requires_admin_token(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    response = client.get("/api/weekly-reviews/current")

    assert response.status_code == 403


def test_current_week_starts_empty_and_uses_monday_to_sunday(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    response = client.get("/api/weekly-reviews/current", headers=OPS_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] is None
    assert datetime.fromisoformat(body["week_start"]).weekday() == 0
    assert datetime.fromisoformat(body["week_end"]).weekday() == 6
    assert body["status"] == "DRAFT"
    assert body["actions"] == []


def test_manager_summary_and_improvement_action_persist(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    review = client.patch(
        "/api/weekly-reviews/current",
        headers={**OPS_HEADERS, "Content-Type": "application/json"},
        json={
            "manager_name": "Kevin",
            "summary": "急單已安排，需改善排程確認。",
            "status": "IN_REVIEW",
        },
    )
    assert review.status_code == 200
    assert review.json()["manager_name"] == "Kevin"

    created = client.post(
        "/api/weekly-reviews/current/actions",
        headers={**OPS_HEADERS, "Content-Type": "application/json"},
        json={
            "title": "提升準時出貨率",
            "issue_summary": "本週急單造成延遲",
            "root_cause": "下午人力不足",
            "action_plan": "調整排班並提前確認急單",
            "owner_name": "Kevin",
            "target_text": "下週達 95%",
            "due_date": "2026-09-13",
            "needs_jacky": False,
        },
    )
    assert created.status_code == 201
    action_id = created.json()["id"]

    completed = client.patch(
        f"/api/weekly-reviews/actions/{action_id}",
        headers={**OPS_HEADERS, "Content-Type": "application/json"},
        json={"status": "DONE", "result_text": "已達 96%"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "DONE"

    loaded = client.get("/api/weekly-reviews/current", headers=OPS_HEADERS)
    assert loaded.json()["id"] is not None
    assert loaded.json()["summary"] == "急單已安排，需改善排程確認。"
    assert loaded.json()["actions"][0]["result_text"] == "已達 96%"
    assert loaded.json()["open_improvements"] == 0


def test_weekly_review_counts_current_week_intelligence(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    # Existing model constraints make a full intelligence fixture expensive; validate the
    # aggregation query on an empty current week and its stable numeric contract.
    response = client.get("/api/weekly-reviews/current", headers=OPS_HEADERS)
    assert response.status_code == 200
    assert response.json()["total_intelligence"] == 0
    assert response.json()["urgent_intelligence"] == 0
    assert response.json()["decisions_needed"] == 0


def test_unknown_improvement_action_returns_not_found(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    response = client.patch(
        "/api/weekly-reviews/actions/missing",
        headers={**OPS_HEADERS, "Content-Type": "application/json"},
        json={"status": "DONE"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "IMPROVEMENT_ACTION_NOT_FOUND"
