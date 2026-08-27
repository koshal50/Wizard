"""
VLLMProvider: a real LLMProvider backed by a self-hosted, open-source
model served through vLLM's OpenAI-compatible API.

This is the intended real runtime provider (no per-token cost, no vendor
lock-in). Structured output is enforced the same way across providers:
append the target Pydantic model's JSON Schema to the system prompt, then
validate the returned JSON with `model_validate(...)`.

Config (env vars, never hard-coded secrets):
  WIZARD_LLM_BASE_URL  base URL of the vLLM server (default http://localhost:8000)
  WIZARD_LLM_MODEL     open-source model name served by vLLM (required)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import LLMError, LLMProvider

T = TypeVar("T", bound=BaseModel)

DEFAULT_BASE_URL = "http://localhost:8000"

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class VLLMProvider(LLMProvider):
    """Structured-output provider talking to vLLM's `/v1/chat/completions`."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get("WIZARD_LLM_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self._model = model or os.environ.get("WIZARD_LLM_MODEL")
        if not self._model:
            raise LLMError(
                "WIZARD_LLM_MODEL is not set. Set it to the open-source model name "
                "served by your vLLM instance (e.g. 'Qwen/Qwen2.5-7B-Instruct')."
            )
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "vllm"

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
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            response = httpx.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001 - surface any HTTP/network failure uniformly
            raise LLMError(f"vLLM API call failed: {exc}") from exc

        try:
            raw_text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError, TypeError) as exc:
            raise LLMError(f"Unexpected vLLM response shape: {data!r}") from exc
        if not raw_text:
            raise LLMError("vLLM API returned empty content")

        parsed = self._extract_json(raw_text)
        try:
            return response_model.model_validate(parsed)
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
