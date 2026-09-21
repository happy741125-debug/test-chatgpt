from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import Context, ExtractionComparison

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _seed_comparison(database, *, primary_summary: str, shadow_summary: str) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)
    with database.session_factory() as session:
        session.add(
            Context(
                id="ctx-cmp",
                channel_id="ch-cmp",
                start_at=now,
                end_at=now + timedelta(minutes=5),
                version=1,
            )
        )
        session.add(
            ExtractionComparison(
                id="cmp-1",
                context_id="ctx-cmp",
                context_version=1,
                primary_provider="rule-based",
                primary_model="rules-v1",
                primary_output_json={"summary": primary_summary},
                shadow_provider="gemini",
                shadow_model="gemini-2.5-flash",
                shadow_status="SUCCEEDED",
                shadow_output_json={"summary": shadow_summary},
                agreement="PARTIAL",
                diff_json={},
            )
        )
        session.commit()


def test_comparisons_expose_both_summaries(test_context) -> None:
    client, database, _ = test_context
    _seed_comparison(
        database,
        primary_summary="缺貨 缺貨 已出貨 已出貨 訂單 訂單",  # rule-based 貼原文感
        shadow_summary="甲廠商回報缺貨，Kevin 已請補貨，明天下午到。",  # AI 白話
    )

    rows = client.get("/api/ai/comparisons", headers=OPS_HEADERS).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["primary_summary"] == "缺貨 缺貨 已出貨 已出貨 訂單 訂單"
    assert row["shadow_summary"] == "甲廠商回報缺貨，Kevin 已請補貨，明天下午到。"


def test_comparisons_redact_sensitive_summary(test_context) -> None:
    client, database, _ = test_context
    _seed_comparison(
        database,
        primary_summary="請撥打 0912345678 聯絡",
        shadow_summary="客戶電話 0912345678 已通知",
    )
    row = client.get("/api/ai/comparisons", headers=OPS_HEADERS).json()[0]
    # Phone numbers must be masked before display.
    assert "0912345678" not in row["primary_summary"]
    assert "0912345678" not in row["shadow_summary"]


def test_comparisons_require_ops_token(test_context) -> None:
    client, _, _ = test_context
    assert client.get("/api/ai/comparisons").status_code == 403
    assert client.get("/api/ai/comparisons/summary").status_code == 403
