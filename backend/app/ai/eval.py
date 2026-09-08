"""Score an extraction provider against a labelled golden dataset.

Provider-agnostic: works for the rule-based provider today and the Gemini /
OpenAI providers later, since they all expose ``analyze(request)``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.providers import AIProvider, AnalysisMessage, AnalysisRequest
from app.ai.schemas import ContextAnalysisOutput

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

    @property
    def misses(self) -> list[CaseResult]:
        return [result for result in self.results if not result.passed]


def load_cases(path: str | Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data["cases"])


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
    return ScoreReport(total=len(results), passed=passed, accuracy=accuracy, results=results)


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
    return "\n".join(lines)


def main() -> None:  # pragma: no cover - simple CLI
    from app.ai.providers import RuleBasedAIProvider

    report = score_provider(RuleBasedAIProvider(), load_cases())
    print(format_report(report, provider_name="rule-based"))


if __name__ == "__main__":  # pragma: no cover
    main()
