"""One strict model transport for planning and tactical Runtime decisions."""
from __future__ import annotations

import json
import os
import time
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from wizard_kernel.control import flow_trace
from wizard_kernel.ports.cerebras_gate import CerebrasRateGate, retry_after_seconds


class ModelFailure(RuntimeError):
    def __init__(self, kind, detail, status=None, request_id=None):
        super().__init__(flow_trace.safe_text(detail))
        self.kind, self.status, self.request_id = kind, status, request_id


def strict_schema(model):
    schema = model.model_json_schema()
    def close(value, schema_node=True):
        if isinstance(value, dict):
            if schema_node:
                for metadata in ("title", "default", "description"):
                    value.pop(metadata, None)
            value.pop("discriminator", None)
            if "oneOf" in value:
                value["anyOf"] = value.pop("oneOf")
            if value.get("type") == "object":
                value["additionalProperties"] = False
                value["required"] = list(value.get("properties", {}))
            for key, item in value.items():
                close(item, schema_node=key not in {"properties", "$defs", "definitions"})
        elif isinstance(value, list):
            for item in value:
                close(item)
    close(schema)
    return schema


def _safe_response_shape(content):
    """Diagnostic shape only; never used to repair or accept invalid output."""
    try:
        packet = json.loads(content)
    except (ValueError, TypeError):
        return {"json_complete": False}
    if not isinstance(packet, dict):
        return {"root_type": type(packet).__name__}
    decision = packet.get("decision")
    if not isinstance(decision, dict):
        return {"decision_type": type(decision).__name__}
    kind = decision.get("kind")
    result = {"kind": kind if kind in {"tool", "refine", "evaluate", "blocked"} else "unrecognized",
              "has_action": decision.get("action") is not None,
              "has_refinement": decision.get("refinement") is not None}
    refinement = decision.get("refinement")
    if isinstance(refinement, dict) and isinstance(refinement.get("assertions"), list):
        result["assertion_shapes"] = [{
            "source": a.get("source") if a.get("source") in {"repository", "command", "process", "http", "browser"} else "unrecognized",
            "field": a.get("field") if a.get("field") in {"content", "exists", "exit_code", "is_running", "active", "status_code", "body_preview", "url", "title", "snapshot"} else "unrecognized",
            "expected_type": type(a.get("expected")).__name__}
            for a in refinement["assertions"][:4] if isinstance(a, dict)]
    return result


class ModelPolicy:
    requires_verifier = True
    def __init__(self):
        self.base_url = os.environ.get("WIZARD_LLM_BASE_URL", "https://api.cerebras.ai").rstrip("/")
        self.model = os.environ.get("WIZARD_LLM_MODEL", "gpt-oss-120b")
        self.key = os.environ.get("CEREBRAS_KEY") or os.environ.get("OPENAI_API_KEY")
        if not self.key:
            raise ModelFailure("configuration", "Cerebras API key is unavailable to Runtime")
        self.gate = CerebrasRateGate() if urlsplit(self.base_url).hostname == "api.cerebras.ai" else None
        self.provider_requests = 0
        self.last_metadata = {}

    def request(self, role, context, response_model, *, max_input_chars=60000, cancel_check=None, deadline=None, on_progress=None):
        from wizard_kernel.ports.prompts import PLAN, DECIDE, VERIFY
        schema = strict_schema(response_model)
        messages = [{"role": "system", "content": {"planner": PLAN, "explorer": DECIDE, "verifier": VERIFY}[role]},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
        size = len(json.dumps(messages)) + len(json.dumps(schema))
        if size > max_input_chars:
            raise ModelFailure("context_budget", f"Final request size {size} exceeds {max_input_chars} characters")
        payload = {"model": self.model, "temperature": 0, "max_completion_tokens": 1024,
                   "stream": False, "messages": messages,
                   "response_format": {"type": "json_schema", "json_schema": {
                       "name": response_model.__name__, "strict": True, "schema": schema}}}
        if self.gate and self.model == "gpt-oss-120b":
            payload["reasoning_effort"] = "low"
        def progress(stage, **details):
            if on_progress:
                on_progress(stage, {"model": self.model, **details})
        if self.gate:
            if on_progress:
                self.gate.acquire(cancel_check=cancel_check,
                                  on_wait=lambda wait: progress("waiting", wait_seconds=round(wait, 1)))
            else:
                self.gate.acquire(cancel_check=cancel_check)
        if cancel_check:
            cancel_check()
        timeout = min(60, max(0.1, deadline-time.monotonic())) if deadline else 60
        progress("request", timeout_seconds=round(timeout, 1))
        started = time.monotonic()
        try:
            self.provider_requests += 1
            response = httpx.post(self.base_url + "/v1/chat/completions", json=payload,
                                  headers={"Authorization": "Bearer " + self.key},
                                  timeout=timeout)
        except httpx.HTTPError as exc:
            from wizard_kernel.storage.usage import observe
            observe("provider_response", None, role, self.model)
            progress("failure", failure_kind="transport", detail=type(exc).__name__)
            raise ModelFailure("transport", type(exc).__name__) from exc
        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        from wizard_kernel.storage.usage import observe
        observe("provider_response", response, role, self.model)
        self.last_metadata = {"provider_status": response.status_code, "request_id": request_id,
                              "model": self.model, "input_chars": size, "schema": response_model.__name__}
        progress("response", status=response.status_code, elapsed_seconds=round(time.monotonic()-started, 1), request_id=request_id)
        if response.status_code == 429 and self.gate:
            self.gate.defer(retry_after_seconds(response.headers))
        if response.is_error:
            raise ModelFailure("http", response.text.replace(self.key, "[REDACTED]"), response.status_code, request_id)
        try:
            data = response.json()
            choice = data["choices"][0]
            finish = choice.get("finish_reason")
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelFailure("provider_shape", "Provider returned an invalid response envelope", request_id=request_id) from exc
        usage = data.get("usage") or {}
        self.last_metadata.update(finish_reason=finish, usage={k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")})
        if finish != "stop":
            usage = data.get("usage") or {}
            raise ModelFailure("incomplete", f"finish_reason={finish}; completion_tokens={usage.get('completion_tokens')}", request_id=request_id)
        try:
            result = response_model.model_validate_json(content)
        except (ValidationError, TypeError) as exc:
            # Preserve the violated contract without persisting provider text,
            # input values, or Pydantic's input-bearing error representation.
            errors = []
            if isinstance(exc, ValidationError):
                for error in exc.errors(include_input=False, include_context=False, include_url=False)[:8]:
                    item = {"location": list(error["loc"]), "type": error["type"]}
                    if error["type"] == "value_error":
                        item["rule"] = error["msg"]
                    errors.append(item)
            self.last_metadata["validation_errors"] = errors
            self.last_metadata["response_shape"] = _safe_response_shape(content)
            detail = "Structured response failed canonical schema validation"
            if errors:
                detail += ": " + json.dumps(errors)
            raise ModelFailure("schema", detail, status=response.status_code, request_id=request_id) from exc
        progress("validated", schema=response_model.__name__)
        return result
