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
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, Optional, Type, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import LLMError, LLMProvider
from app.llm.cerebras_gate import CerebrasRateGate, retry_after_seconds

T = TypeVar("T", bound=BaseModel)

DEFAULT_BASE_URL = "http://localhost:8000"

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_LOG = logging.getLogger(__name__)


class VLLMProvider(LLMProvider):
    """Structured-output provider talking to vLLM's `/v1/chat/completions`."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get("WIZARD_LLM_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self._model = model or os.environ.get("WIZARD_LLM_MODEL")
        if not self._model:
            raise LLMError(
                "WIZARD_LLM_MODEL is not set. Set it to the open-source model name "
                "served by your vLLM instance (e.g. 'Qwen/Qwen2.5-7B-Instruct')."
            )
        self._timeout = timeout
        self._cerebras_gate = CerebrasRateGate() if urlparse(self._base_url).hostname == "api.cerebras.ai" else None

    @property
    def name(self) -> str:
        return "vllm"

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> T:
        strict_schema = bool((metadata or {}).get("strict_json_schema"))
        if strict_schema:
            max_tokens = int((metadata or {}).get("max_completion_tokens", max_tokens))
        schema = response_model.model_json_schema()
        if strict_schema:
            schema = _strict_explorer_schema(schema, metadata or {})
            full_system = f"{system_prompt}\n\nReturn only the single object constrained by the response schema."
        else:
            full_system = (
                f"{system_prompt}\n\n"
                "You MUST respond with ONLY a single JSON object matching this JSON Schema. "
                "No prose, no markdown fences, no explanation before or after the JSON.\n\n"
                f"JSON Schema:\n{json.dumps(schema)}"
            )
        payload = {
            "model": self._model,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": (
                {"type": "json_schema", "json_schema": {
                    "name": "explorer_tool_request" if response_model.__name__ == 'ExplorerOutput' else 'verification_assessment', "strict": True, "schema": schema,
                }} if strict_schema else {"type": "json_object"}
            ),
        }

        reasoning_effort = (metadata or {}).get("reasoning_effort")
        if strict_schema and self._cerebras_gate and self._model == "gpt-oss-120b" and reasoning_effort == "low":
            payload["reasoning_effort"] = "low"

        if strict_schema:
            _LOG.info(
                "structured_output provider=%s model=%s response_format=json_schema "
                "schema=explorer_tool_request strict=true reasoning_effort=%s "
                "max_completion_tokens=%s stream=false prompt_chars=%s schema_chars=%s",
                "cerebras" if self._cerebras_gate else "openai-compatible",
                self._model, payload.get("reasoning_effort", "default"), max_tokens,
                len(system_prompt) + len(user_prompt), len(json.dumps(schema)),
            )

        api_key = os.environ.get("OPENAI_API_KEY")
        deadline_text = ((metadata or {}).get('input') or {}).get('investigation', {}).get('operation_deadline_at') or ((metadata or {}).get('input') or {}).get('investigation', {}).get('deadline_at') or (metadata or {}).get('deadline_at')
        deadline = datetime.fromisoformat(deadline_text).timestamp() if deadline_text else time.time() + self._timeout
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        for attempt in range(2 if self._cerebras_gate else 1):
            if self._cerebras_gate:
                self._cerebras_gate.acquire(deadline=deadline)
            remaining = deadline - time.time()
            if remaining <= 0:
                raise LLMError('Investigation deadline reached before provider request')
            try:
                response = httpx.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=min(self._timeout, remaining),
                )
            except Exception as exc:  # noqa: BLE001 - surface any HTTP/network failure uniformly
                raise LLMError(f"vLLM API call failed: {exc}") from exc
            if response.status_code == 429 and self._cerebras_gate:
                wait = retry_after_seconds(response.headers)
                self._cerebras_gate.defer(wait)
                if attempt == 0:
                    _LOG.info('{"event":"provider_retry_wait","provider":"cerebras","wait_seconds":%.3f}', wait)
                    _LOG.info('{"event":"provider_retry","provider":"cerebras","attempt":1}')
                    continue
                _LOG.warning('{"event":"provider_429","provider":"cerebras","retry_exhausted":true}')
            try:
                response.raise_for_status()
                data = response.json()
                break
            except httpx.HTTPStatusError as exc:
                response = exc.response
                body = re.sub(
                    r"(?i)(authorization|(?:cerebras|openai|groq)?[_ -]?api[_ -]?key|token|secret|password)(\s*[=:]\s*)[^,}\s]+",
                    r"\1\2[REDACTED]",
                    response.text[:2000],
                )
                safe_headers = {
                    key: value for key, value in response.headers.items()
                    if key.lower() == "retry-after"
                    or "ratelimit" in key.lower()
                    or key.lower() in ("request-id", "x-request-id")
                }
                raise LLMError(
                    f"vLLM API HTTP {response.status_code}: {body}; rate-limit headers={safe_headers}"
                ) from exc
            except Exception as exc:  # noqa: BLE001 - surface any HTTP/network failure uniformly
                raise LLMError(f"vLLM API call failed: {exc}") from exc

        try:
            choice = data["choices"][0]
            raw_text = choice["message"]["content"].strip()
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, AttributeError, TypeError) as exc:
            raise LLMError(f"Unexpected vLLM response shape: {data!r}") from exc
        if not raw_text:
            raise LLMError("vLLM API returned empty content")

        if strict_schema:
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
                usage = data.get("usage") or {}
                raise LLMError(
                    f"{response_model.__name__} structured response invalid JSON; "
                    f"finish_reason={finish_reason or 'unknown'}; "
                    f"completion_tokens={usage.get('completion_tokens', 'unknown')}; "
                    f"content_chars={len(raw_text)}; request_id={request_id or 'unknown'}"
                ) from exc
        else:
            parsed = self._extract_json(raw_text)
        try:
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            if strict_schema:
                request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
                raise LLMError(
                    f"{response_model.__name__} structured response failed schema validation; "
                    f"finish_reason={finish_reason or 'unknown'}; request_id={request_id or 'unknown'}; "
                    f"detail={str(exc)[:400]}"
                ) from exc
            raise LLMError(f"LLM response failed schema validation: {exc}") from exc

    @staticmethod
    def _extract_json(raw_text: str) -> Dict[str, Any]:
        fence_match = _JSON_FENCE_RE.search(raw_text)
        candidate = fence_match.group(1) if fence_match else raw_text
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM response was not valid JSON: {exc}\nRaw response: {raw_text[:500]}") from exc


def _strict_explorer_schema(schema: dict, metadata: dict) -> dict:
    """Constrain each nested ToolRequest variant under strict decoding."""
    def close_objects(value):
        if isinstance(value, dict):
            if value.get("type") == "object":
                value["additionalProperties"] = False
                if 'properties' in value:
                    value['required'] = list(value['properties'])
            for child in value.values():
                close_objects(child)
        elif isinstance(value, list):
            for child in value:
                close_objects(child)

    close_objects(schema)
    available = (metadata.get("input") or {}).get("available_tools") or []
    enum_schema = schema.get("$defs", {}).get("ToolName")
    if enum_schema is not None and available:
        enum_schema["enum"] = [item for item in enum_schema.get("enum", []) if item in available]

    parameter_contracts = metadata.get("tool_parameter_schema") or {}
    type_map = {"string": "string", "integer": "integer", "number": "number", "boolean": "boolean"}
    properties = schema.get("properties", {})
    if 'report_markdown' in properties and 'tool_request' not in properties:
        # Verification uses the same strict-object closure, but has no tool/node
        # union. Do not validate its schema as an Explorer response.
        return schema
    if not {"investigation_id", "node_id", "tool_request"} <= set(properties):
        raise LLMError("Explorer structured schema has no parameters object")
    # IDs are supplied by the current Runtime dispatch, never inferred from history.
    current_input = metadata.get('input') or {}
    for field, value in (
        ('investigation_id', current_input.get('investigation_id')),
        ('node_id', (current_input.get('current_node') or {}).get('node_id')),
    ):
        if value:
            properties[field] = {'type': 'string', 'enum': [value]}
    branches = []
    for tool in available:
        param_properties = {
            name: {"type": type_map[kind]}
            for name, kind in parameter_contracts.get(tool, {}).items()
            if kind in type_map
        }
        tool_properties = {
            "tool": {"type": "string", "enum": [tool]},
            "parameters": {
                "type": "object", "properties": param_properties,
                "required": list(param_properties), "additionalProperties": False,
            },
        }
        branches.append({
            "type": "object", "properties": tool_properties,
            "required": list(tool_properties), "additionalProperties": False,
        })
    schema["properties"]["tool_request"] = {"anyOf": branches + [{"type": "null"}]}
    schema['required'] = list(schema['properties'])
    return schema
