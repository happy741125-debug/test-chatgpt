from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AnalysisMessage:
    id: str
    sequence: int
    sender_identity_id: str | None
    message_type: str
    text: str | None
    source_created_at: str


@dataclass(frozen=True)
class AnalysisRequest:
    context_id: str
    context_version: int
    timezone: str
    reference_time: str
    prompt_name: str
    prompt_version: int
    prompt_template: str
    messages: tuple[AnalysisMessage, ...]


@dataclass(frozen=True)
class ProviderResponse:
    output: dict[str, Any]
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_microunits: int | None = None


class AIProvider(Protocol):
    name: str
    model: str

    def analyze(self, request: AnalysisRequest) -> ProviderResponse: ...


MockOutput = dict[str, Any] | Callable[[AnalysisRequest], dict[str, Any]]


class MockAIProvider:
    """Deterministic provider for CI; it never makes a network request."""

    name = "mock"
    model = "mock-intelligence-v1"

    def __init__(self, output: MockOutput) -> None:
        self.output = output
        self.requests: list[AnalysisRequest] = []

    def analyze(self, request: AnalysisRequest) -> ProviderResponse:
        self.requests.append(request)
        output = self.output(request) if callable(self.output) else self.output
        return ProviderResponse(
            output=output,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_microunits=0,
        )
