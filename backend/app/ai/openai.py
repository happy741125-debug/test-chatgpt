from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.ai.prompt import build_extraction_prompt
from app.ai.providers import AnalysisRequest, ProviderResponse

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Deliberately rough, conservative microunit estimate; keeps cost non-zero
# without pretending to track any exact price sheet.
_INPUT_MICROUNITS_PER_1K = 150
_OUTPUT_MICROUNITS_PER_1K = 600

# invoke(url, headers, body) -> parsed OpenAI JSON response. Injectable so tests
# never touch the network.
OpenAIInvoke = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class OpenAIProviderError(RuntimeError):
    """Raised when OpenAI returns something we cannot turn into structured output."""


class OpenAIAIProvider:
    """OpenAI Chat Completions extractor. Used only in shadow mode."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        timeout: float = 20.0,
        invoke: OpenAIInvoke | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._invoke = invoke or self._http_invoke

    def analyze(self, request: AnalysisRequest) -> ProviderResponse:
        prompt = build_extraction_prompt(request)
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        raw = self._invoke(OPENAI_ENDPOINT, headers, body)
        output = _parse_output(raw)
        usage = raw.get("usage") if isinstance(raw, dict) else None
        input_tokens = _int_or_none(usage, "prompt_tokens")
        output_tokens = _int_or_none(usage, "completion_tokens")
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
        raise OpenAIProviderError("OpenAI response was not a JSON object")
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAIProviderError("OpenAI response had no choices")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    payload = (message.get("content") or "").strip()
    if not payload:
        raise OpenAIProviderError("OpenAI choice contained no content")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise OpenAIProviderError("OpenAI did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise OpenAIProviderError("OpenAI JSON was not an object")
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
