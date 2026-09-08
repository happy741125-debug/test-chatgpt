from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _revenue_workbook(*, wrong_total: bool = False) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    periods = ["202601", "202602", "202603", "202604", "202605", "202606"]
    for index, period in enumerate(periods):
        sheet = workbook.create_sheet(period)
        sheet.append(
            ["倉別", "客戶", "倉租費", "理貨系統費", "物流運送費", "加工費", "總金額\n(未稅)"]
        )
        declining = 100_000 if index < 3 else 30_000
        rows = [
            ["汐止", "1001 第一客戶", 400_000, 100_000, 0, 0, 500_000],
            ["淡水", "1002 第二客戶", 200_000, 100_000, 0, 0, 300_000],
            ["汐止", "1003 衰退客戶", declining, 0, 0, 0, declining],
            ["淡水", "1004 成長客戶", 20_000 + index * 20_000, 0, 0, 0, 20_000 + index * 20_000],
        ]
        for row in rows:
            sheet.append(row)
        total = sum(row[-1] for row in rows)
        source_total = total - 123 if wrong_total and index == 5 else total
        sheet.append([None, "總金額", None, None, None, None, source_total])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_revenue_dashboard_requires_admin_token(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    response = client.get("/api/revenue/dashboard")

    assert response.status_code == 403


def test_revenue_import_builds_dashboard_without_storing_original(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    content = _revenue_workbook()

    imported = client.post(
        "/api/revenue/imports",
        headers=OPS_HEADERS,
        files={
            "file": (
                "營收數據表.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert imported.status_code == 201
    assert imported.json()["period_count"] == 6
    assert imported.json()["record_count"] == 24
    assert imported.json()["duplicate"] is False

    dashboard = client.get("/api/revenue/dashboard", headers=OPS_HEADERS).json()
    assert dashboard["has_data"] is True
    assert dashboard["current"]["period"] == "2026-06"
    assert dashboard["current"]["total"] == 950_000
    assert dashboard["concentration"]["top2_pct"] > 80
    assert dashboard["concentration"]["risk_level"] == "RED"
    assert dashboard["months"][0]["period"] == "2026-01"
    assert dashboard["latest_import"]["filename"] == "營收數據表.xlsx"
    assert "content" not in dashboard["latest_import"]

    executive = client.get("/api/dashboard/ceo", headers=OPS_HEADERS).json()
    revenue = next(item for item in executive["metrics"] if item["code"] == "REVENUE")
    assert revenue["current_value"] == 95
    assert revenue["source_label"] == "營收數據表匯入"


def test_same_workbook_is_idempotent(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    content = _revenue_workbook()
    files = {
        "file": (
            "revenue.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    first = client.post("/api/revenue/imports", headers=OPS_HEADERS, files=files)
    second = client.post("/api/revenue/imports", headers=OPS_HEADERS, files=files)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["duplicate"] is True
    dashboard = client.get("/api/revenue/dashboard", headers=OPS_HEADERS).json()
    assert dashboard["current"]["total"] == 950_000


def test_import_reports_formula_total_difference_and_review_signals(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    content = _revenue_workbook(wrong_total=True)

    imported = client.post(
        "/api/revenue/imports",
        headers=OPS_HEADERS,
        files={
            "file": (
                "revenue.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    dashboard = client.get("/api/revenue/dashboard", headers=OPS_HEADERS).json()
    weekly = client.get("/api/weekly-reviews/current", headers=OPS_HEADERS).json()

    assert imported.json()["warning_count"] == 1
    assert dashboard["issues"][0]["code"] == "MONTH_TOTAL_MISMATCH"
    assert dashboard["issues"][0]["difference"] == 123
    assert {signal["code"] for signal in weekly["metric_signals"]} >= {
        "REVENUE_CONCENTRATION",
        "CUSTOMER_REVENUE_DECLINE",
    }


def test_revenue_import_rejects_non_excel(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    response = client.post(
        "/api/revenue/imports",
        headers=OPS_HEADERS,
        files={"file": ("revenue.csv", b"not excel", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "INVALID_REVENUE_FILE"
