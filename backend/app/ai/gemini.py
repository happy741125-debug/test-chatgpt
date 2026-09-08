from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.ai.prompt import build_extraction_prompt
from app.ai.providers import AnalysisRequest, ProviderResponse

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Gemini 1.5/2.x flash pricing is well under this; we keep a deliberately rough,
# conservative estimate so cost never reads as free while staying provider-agnostic.
_INPUT_MICROUNITS_PER_1K = 100
_OUTPUT_MICROUNITS_PER_1K = 300

# invoke(url, headers, body) -> parsed Gemini JSON response. Injectable so tests
# never touch the network.
GeminiInvoke = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class GeminiProviderError(RuntimeError):
    """Raised when Gemini returns something we cannot turn into structured output."""


class GeminiAIProvider:
    """Google Gemini extractor. Used only in shadow mode; never blocks the primary."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash",
        timeout: float = 20.0,
        invoke: GeminiInvoke | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._invoke = invoke or self._http_invoke

    def analyze(self, request: AnalysisRequest) -> ProviderResponse:
        prompt = build_extraction_prompt(request)
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            },
        }
        # The API key travels in a header, never in the URL/query string.
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._api_key}
        url = GEMINI_ENDPOINT.format(model=self.model)
        raw = self._invoke(url, headers, body)
        output = _parse_output(raw)
        usage = raw.get("usageMetadata") if isinstance(raw, dict) else None
        input_tokens = _int_or_none(usage, "promptTokenCount")
        output_tokens = _int_or_none(usage, "candidatesTokenCount")
        return ProviderResponse(
            output=output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_microunits=_estimate_cost(input_tokens, output_tokens),
        )

    def _http_invoke(
        self, url: str, headers: dict[str, str], body: dict[str, Any]
    ) -> dict[str, Any]:
        import httpx

        response = httpx.post(url, headers=headers, json=body, timeout=self._timeout)
        response.raise_for_status()
        return response.json()


def _parse_output(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GeminiProviderError("Gemini response was not a JSON object")
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiProviderError("Gemini response had no candidates")
    parts = (
        candidates[0].get("content", {}).get("parts", [])
        if isinstance(candidates[0], dict)
        else []
    )
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    payload = "".join(texts).strip()
    if not payload:
        raise GeminiProviderError("Gemini candidate contained no text")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise GeminiProviderError("Gemini did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise GeminiProviderError("Gemini JSON was not an object")
    return parsed


def _int_or_none(usage: object, key: str) -> int | None:
    if isinstance(usage, dict) and isinstance(usage.get(key), int):
        return int(usage[key])
    return None


def _estimate_cost(input_tokens: int | None, output_tokens: int | None) -> int:
    cost = 0
    if input_tokens:
        cost += input_tokens * _INPUT_MICROUNITS_PER_1K // 1000
    if output_tokens:
        cost += output_tokens * _OUTPUT_MICROUNITS_PER_1K // 1000
    return cost
