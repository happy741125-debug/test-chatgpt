from __future__ import annotations

from app.ai.eval import format_report, load_cases, score_provider
from app.ai.providers import MockAIProvider, RuleBasedAIProvider


def test_golden_dataset_is_usable() -> None:
    cases = load_cases()
    assert len(cases) >= 15
    # Every case is well-formed.
    for case in cases:
        assert case["id"]
        assert isinstance(case["work_related"], bool)
        if case["work_related"]:
            assert case["expected_category"], case["id"]


def test_rule_provider_meets_baseline_and_reports_misses() -> None:
    cases = load_cases()
    report = score_provider(RuleBasedAIProvider(), cases)

    # Regression guard: the rule engine should clear a sensible bar on real
    # phrasings. Printed so CI logs show the scorecard.
    print("\n" + format_report(report, provider_name="rule-based"))
    assert report.accuracy >= 0.75

    # The two documented blind spots should surface as misses (they motivate the
    # LLM), and the clear operational cases should pass.
    miss_ids = {miss.id for miss in report.misses}
    assert {"inbound-already-done", "system-api-key-gap"}.issubset(miss_ids)
    passed_ids = {r.id for r in report.results if r.passed}
    assert {"shortage-chain", "urgent-rush-today", "quote-request"}.issubset(passed_ids)


def test_harness_is_provider_agnostic() -> None:
    # A provider that always returns noise should score only the noise cases.
    noise = {
        "work_related": False,
        "noise_type": "GENERAL_CHAT",
        "summary": "無營運事件。",
        "entities": [],
        "items": [],
        "overall_confidence": 0.9,
    }
    report = score_provider(MockAIProvider(noise), load_cases())
    noise_cases = sum(1 for c in load_cases() if not c["work_related"])
    assert report.passed == noise_cases
