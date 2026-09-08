"""Score an extraction provider against a labelled golden dataset.

Provider-agnostic: works for the rule-based provider today and the Gemini /
OpenAI providers later, since they all expose ``analyze(request)``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.order_ids import extract_order_ids
from app.ai.providers import AIProvider, AnalysisMessage, AnalysisRequest
from app.ai.schemas import ContextAnalysisOutput
from app.intelligence.attention import classify_attention
from app.intelligence.signals import detect_blocker, detect_lifecycle_stage

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "tests" / "data" / "golden_extraction.json"


@dataclass(frozen=True)
class CaseResult:
    id: str
    passed: bool
    expected_work_related: bool
    expected_category: str | None
    detected_work_related: bool
    detected_categories: list[str]


@dataclass(frozen=True)
class ScoreReport:
    total: int
    passed: int
    accuracy: float
    results: list[CaseResult]
    category_metrics: dict[str, dict[str, float | int]]

    @property
    def misses(self) -> list[CaseResult]:
        return [result for result in self.results if not result.passed]


@dataclass(frozen=True)
class DimensionScore:
    passed: int
    total: int

    @property
    def accuracy(self) -> float:
        return round(self.passed / self.total, 3) if self.total else 0.0


def load_cases(path: str | Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    transforms = (
        lambda text: text,
        lambda text: f"更新：{text}",
        lambda text: f"麻煩協助確認，{text}",
        lambda text: f"{text}，謝謝",
        lambda text: text.replace("，", "\n", 1),
        lambda text: f"群組訊息｜{text}",
    )
    for case in data["cases"]:
        for index, transform in enumerate(transforms, start=1):
            variant = dict(case)
            variant["id"] = f"{case['id']}-v{index}"
            variant["text"] = transform(case["text"])
            cases.append(variant)
    return cases


def _request_from_text(text: str, case_id: str) -> AnalysisRequest:
    return AnalysisRequest(
        context_id=case_id,
        context_version=1,
        timezone="Asia/Taipei",
        reference_time="2026-09-08T12:00:00+08:00",
        prompt_name="context-intelligence",
        prompt_version=1,
        prompt_template="",
        messages=(
            AnalysisMessage(
                id=f"{case_id}-m1",
                sequence=1,
                sender_identity_id=None,
                message_type="text",
                text=text,
                source_created_at="2026-09-08T04:00:00+00:00",
            ),
        ),
    )


def score_provider(provider: AIProvider, cases: list[dict[str, Any]]) -> ScoreReport:
    results: list[CaseResult] = []
    for case in cases:
        response = provider.analyze(_request_from_text(case["text"], case["id"]))
        output = ContextAnalysisOutput.model_validate(response.output)
        categories = sorted({item.event_type_code for item in output.items})
        expected_work_related = bool(case["work_related"])
        expected_category = case.get("expected_category")
        if not expected_work_related:
            passed = output.work_related is False
        else:
            passed = output.work_related and expected_category in categories
        results.append(
            CaseResult(
                id=case["id"],
                passed=passed,
                expected_work_related=expected_work_related,
                expected_category=expected_category,
                detected_work_related=output.work_related,
                detected_categories=categories,
            )
        )
    passed = sum(1 for result in results if result.passed)
    accuracy = round(passed / len(results), 3) if results else 0.0
    return ScoreReport(
        total=len(results),
        passed=passed,
        accuracy=accuracy,
        results=results,
        category_metrics=_category_metrics(results),
    )


def _category_metrics(results: list[CaseResult]) -> dict[str, dict[str, float | int]]:
    categories = sorted(
        {result.expected_category for result in results if result.expected_category}
        | {category for result in results for category in result.detected_categories}
    )
    metrics: dict[str, dict[str, float | int]] = {}
    for category in categories:
        true_positive = sum(
            result.expected_category == category and category in result.detected_categories
            for result in results
        )
        false_positive = sum(
            result.expected_category != category and category in result.detected_categories
            for result in results
        )
        false_negative = sum(
            result.expected_category == category and category not in result.detected_categories
            for result in results
        )
        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        metrics[category] = {
            "support": true_positive + false_negative,
            "precision": round(true_positive / precision_denominator, 3)
            if precision_denominator
            else 0.0,
            "recall": round(true_positive / recall_denominator, 3)
            if recall_denominator
            else 0.0,
        }
    return metrics


def format_report(report: ScoreReport, *, provider_name: str = "") -> str:
    header = f"抽取評分{f'（{provider_name}）' if provider_name else ''}：" + (
        f"{report.passed}/{report.total} 通過，準確率 {report.accuracy:.0%}"
    )
    lines = [header]
    if report.misses:
        lines.append("未通過：")
        for miss in report.misses:
            expected = miss.expected_category or "（雜訊）"
            got = ",".join(miss.detected_categories) or "（無/判為雜訊）"
            lines.append(f"  - {miss.id}: 預期 {expected}，實得 {got}")
    lines.append("分類 Precision / Recall：")
    for category, metrics in report.category_metrics.items():
        lines.append(
            f"  - {category}: P {metrics['precision']:.0%} / "
            f"R {metrics['recall']:.0%} / n={metrics['support']}"
        )
    return "\n".join(lines)


def score_quality_dimensions(provider: AIProvider) -> dict[str, DimensionScore]:
    status_cases = (
        ("今日已入庫", "INBOUND_RECEIVED"),
        ("訂單已出貨", "OUTBOUND_SHIPPED"),
        ("客戶已簽收", "DELIVERED"),
        ("客戶表示已匯款", "PAYMENT_REPORTED"),
        ("財務確認入帳", "PAYMENT_RECONCILED"),
        ("系統已恢復正常", "SYSTEM_RECOVERED"),
    )
    blocker_cases = (
        ("商品缺貨，目前調不到", "STOCK"),
        ("待補件，資料尚未提供", "DOCUMENT"),
        ("等客戶回覆", "CUSTOMER_WAITING"),
        ("WMS 異常", "SYSTEM"),
        ("現場人力不足", "CAPACITY"),
        ("款項未入帳", "PAYMENT"),
    )
    attention_cases = (
        (["TASK"], "P2", False, "TEAM"),
        (["DECISION_REQUIRED"], "P1", True, "BOSS"),
        (["RISK"], "P0", False, "BOSS"),
        (["FYI"], "P3", False, "TEAM"),
    )
    status_passed = sum(detect_lifecycle_stage(text) == expected for text, expected in status_cases)
    blocker_passed = sum(detect_blocker(text) == expected for text, expected in blocker_cases)
    attention_passed = sum(
        classify_attention(
            facets=facets,
            priority_level=priority,
            requires_user_action=requires_action,
        ).level
        == expected
        for facets, priority, requires_action, expected in attention_cases
    )
    deadline_texts = ("明天安排出貨", "明天下午安排出貨", "今天安排出貨")
    deadline_passed = 0
    entity_passed = 0
    for index, text in enumerate(deadline_texts):
        output = ContextAnalysisOutput.model_validate(
            provider.analyze(_request_from_text(text, f"deadline-{index}")).output
        )
        deadline_passed += int(any(item.deadline is not None for item in output.items))
    for index, text in enumerate(("甲客戶急單明天出貨", "乙客戶反映缺件")):
        output = ContextAnalysisOutput.model_validate(
            provider.analyze(_request_from_text(text, f"entity-{index}")).output
        )
        entity_passed += int(any(entity.type.value == "CUSTOMER" for entity in output.entities))
    duplicate_cases = (
        ("ORD-20260908-0001 急單", "ORD-20260908-0001 已出貨", True),
        ("INB-20260908-0002 待入庫", "INB-20260908-0002 已入庫", True),
        ("WO-20260908-003 加工", "WO-20260908-004 加工", False),
        ("沒有單號的事件甲", "沒有單號的事件乙", False),
    )
    duplicate_passed = sum(
        bool(set(extract_order_ids(left)) & set(extract_order_ids(right))) == expected
        for left, right, expected in duplicate_cases
    )
    return {
        "entity": DimensionScore(entity_passed, 2),
        "status": DimensionScore(status_passed, len(status_cases)),
        "blocker": DimensionScore(blocker_passed, len(blocker_cases)),
        "attention": DimensionScore(attention_passed, len(attention_cases)),
        "deadline": DimensionScore(deadline_passed, len(deadline_texts)),
        "duplicate": DimensionScore(duplicate_passed, len(duplicate_cases)),
    }


def main() -> None:  # pragma: no cover - simple CLI
    from app.ai.providers import RuleBasedAIProvider

    report = score_provider(RuleBasedAIProvider(), load_cases())
    print(format_report(report, provider_name="rule-based"))
    for name, score in score_quality_dimensions(RuleBasedAIProvider()).items():
        print(f"{name}: {score.passed}/{score.total} ({score.accuracy:.0%})")


if __name__ == "__main__":  # pragma: no cover
    main()
