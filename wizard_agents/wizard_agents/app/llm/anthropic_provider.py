"""
AnthropicProvider: a real LLMProvider implementation backed by the
Anthropic Messages API.

The API key is read from the ANTHROPIC_API_KEY environment variable and
is never hard-coded. If the `anthropic` package or the API key is
missing, construction fails fast with a clear error -- callers should
fall back to MockLLMProvider in that case (see app/llm/__init__.py).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMError, LLMProvider

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-sonnet-4-6"

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class AnthropicProvider(LLMProvider):
    """Structured-output provider using Anthropic's Messages API.

    Structure is enforced by instructing the model to return only JSON
    matching the target pydantic schema, then validating the parsed JSON
    against that schema. This keeps the agent code independent of any
    particular SDK "tool use" / function-calling mechanism.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Set it in the environment or .env file, "
                "or use MockLLMProvider for offline operation."
            )
        try:
            import anthropic  # local import so the package is optional
        except ImportError as exc:  # pragma: no cover - exercised only when dependency missing
            raise LLMError(
                "The 'anthropic' package is required for AnthropicProvider. "
                "Install it with `pip install anthropic`."
            ) from exc

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model or os.environ.get("WIZARD_LLM_MODEL", DEFAULT_MODEL)

    @property
    def name(self) -> str:
        return "anthropic"

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        *,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> T:
        schema = response_model.model_json_schema()
        full_system = (
            f"{system_prompt}\n\n"
            "You MUST respond with ONLY a single JSON object matching this JSON Schema. "
            "No prose, no markdown fences, no explanation before or after the JSON.\n\n"
            f"JSON Schema:\n{json.dumps(schema)}"
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=full_system,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as exc:  # noqa: BLE001 - surface any SDK/network failure uniformly
            raise LLMError(f"Anthropic API call failed: {exc}") from exc

        text_parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        raw_text = "\n".join(text_parts).strip()
        if not raw_text:
            raise LLMError("Anthropic API returned no text content")

        payload = self._extract_json(raw_text)

        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            raise LLMError(f"LLM response failed schema validation: {exc}") from exc

    @staticmethod
    def _extract_json(raw_text: str) -> Dict[str, Any]:
        fence_match = _JSON_FENCE_RE.search(raw_text)
        candidate = fence_match.group(1) if fence_match else raw_text
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM response was not valid JSON: {exc}\nRaw response: {raw_text[:500]}") from exc
