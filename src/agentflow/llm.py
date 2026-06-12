"""LLM access layer.

Agents depend on the narrow `LLMClient` protocol rather than a vendor SDK,
so providers can be swapped (or mocked) without touching graph logic.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from agentflow.config import Settings


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, max_tokens: int = 1024):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


class MockLLM:
    """Deterministic stand-in used in tests and keyless local runs.

    Documents containing the marker word "ambiguous" produce a low-confidence
    classification, which exercises the human-review branch of the graph.
    """

    def complete(self, system: str, prompt: str) -> str:
        low_confidence = "ambiguous" in prompt.lower()
        if "classification agent" in system.lower():
            return json.dumps(
                {
                    "category": "unknown" if low_confidence else "invoice",
                    "confidence": 0.42 if low_confidence else 0.93,
                    "reasoning": "mock classification",
                }
            )
        if "extraction agent" in system.lower():
            return json.dumps(
                {
                    "vendor": "Acme Corp",
                    "invoice_number": "INV-1042",
                    "amount": 1875.50,
                    "currency": "USD",
                    "due_date": "2026-07-01",
                }
            )
        if "validation agent" in system.lower():
            return json.dumps({"valid": True, "issues": []})
        return "{}"


def parse_json_response(text: str) -> dict:
    """Parse a JSON object from an LLM response, tolerating fenced output."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def get_llm(settings: Settings) -> LLMClient:
    if settings.anthropic_api_key and not settings.mock_mode:
        return AnthropicLLM(settings.anthropic_api_key, settings.model, settings.max_tokens)
    return MockLLM()
