from __future__ import annotations

from types import SimpleNamespace

from app.ai.order_ids import extract_order_ids
from app.ai.schemas import ContextAnalysisOutput
from app.intelligence.materializer import _case_key


def test_extract_recognises_all_reference_formats() -> None:
    assert extract_order_ids("新單 ORD-20260731-0001 麻煩了") == ["ORD-20260731-0001"]
    assert extract_order_ids("開立入庫單 INB-20260826-0001") == ["INB-20260826-0001"]
    # legacy system ids: digits + H + digits
    assert extract_order_ids("取消 1042H2608240006、1042H2608240007") == [
        "1042H2608240006",
        "1042H2608240007",
    ]
    assert extract_order_ids("查一筆 1026H2606030002 的裝箱清單") == ["1026H2606030002"]
    # de-duplicated and upper-cased
    assert extract_order_ids("ord-20260731-0001 又提到 ORD-20260731-0001") == [
        "ORD-20260731-0001"
    ]
    assert extract_order_ids("今天天氣很好，沒有單號") == []


def _output(summary: str) -> ContextAnalysisOutput:
    return ContextAnalysisOutput.model_validate(
        {
            "work_related": True,
            "noise_type": None,
            "summary": summary,
            "entities": [],
            "items": [
                {
                    "type": "EVENT",
                    "domain_code": "WAREHOUSE_OPERATIONS",
                    "event_type_code": "OUTBOUND_OPERATION",
                    "title": summary,
                    "summary": summary,
                    "owner_text": None,
                    "deadline": None,
                    "requires_user_action": False,
                    "evidence_message_ids": ["m-1"],
                    "confidence": 0.8,
                }
            ],
            "overall_confidence": 0.8,
        }
    )


def test_legacy_order_id_merges_across_sources() -> None:
    # Same legacy id seen in two different contexts (e.g. LINE then Gmail) must
    # produce the same case_key so the case merges.
    line_ctx = SimpleNamespace(id="ctx-line", version=1)
    gmail_ctx = SimpleNamespace(id="ctx-gmail", version=1)
    line_out = _output("客戶詢問 1042H2608240006 出貨進度")
    gmail_out = _output("Email 確認 1042H2608240006 已寄出")

    assert _case_key(line_ctx, line_out) == _case_key(gmail_ctx, gmail_out)


def test_different_ids_do_not_merge() -> None:
    ctx = SimpleNamespace(id="ctx-a", version=1)
    a = _output("1042H2608240006 的單")
    b = _output("1042H2608240007 的單")
    assert _case_key(ctx, a) != _case_key(ctx, b)


def test_no_id_falls_back_to_context_identity() -> None:
    a = SimpleNamespace(id="ctx-a", version=1)
    b = SimpleNamespace(id="ctx-b", version=1)
    out = _output("沒有任何單號的一般對話")
    # Without a shared id, two different contexts stay separate.
    assert _case_key(a, out) != _case_key(b, out)
