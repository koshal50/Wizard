from __future__ import annotations

import json

import httpx
import pytest

from app.contracts.explorer import ExplorerOutput
from app.explorer.agent import ExplorerAgent
from app.llm.base import LLMError
from app.llm.vllm_provider import VLLMProvider


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self._status = status
        self.status_code = status
        self.headers = {"x-request-id": "req-test"}

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self) -> dict:
        return self._payload


def _content(obj: dict) -> dict:
    """Build an OpenAI-compatible chat.completions payload."""
    return {"choices": [{"message": {"content": json.dumps(obj)}, "finish_reason": "stop"}]}


@pytest.fixture()
def vllm_env(monkeypatch):
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://vllm.local:8000")
    monkeypatch.setenv("WIZARD_LLM_MODEL", "test/open-model")


def _explorer_output_dict() -> dict:
    return ExplorerOutput(
        investigation_id="inv-1",
        node_id="n1",
        tool_request={"tool": "read_file", "parameters": {"path": "."}},
    ).model_dump(mode="json")


def test_requires_model(monkeypatch):
    monkeypatch.delenv("WIZARD_LLM_MODEL", raising=False)
    with pytest.raises(LLMError):
        VLLMProvider()


def test_generate_structured_success(monkeypatch, vllm_env):
    captured = {}

    def fake_post(url, json, timeout, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(_content(_explorer_output_dict()))

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)

    provider = VLLMProvider()
    assert provider.name == "vllm"
    out = provider.generate_structured("sys", "user", ExplorerOutput)

    assert isinstance(out, ExplorerOutput)
    assert out.investigation_id == "inv-1"
    assert captured["url"] == "http://vllm.local:8000/v1/chat/completions"
    assert captured["json"]["model"] == "test/open-model"
    assert captured["json"]["messages"][1]["content"] == "user"
    assert captured["json"]["response_format"]["type"] == "json_object"


def test_explorer_requests_strict_canonical_toolrequest_schema(monkeypatch, vllm_env):
    captured = {}

    def fake_post(url, json, timeout, headers=None):  # noqa: A002
        captured.update(json)
        return _FakeResponse(_content(_explorer_output_dict()))

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)
    metadata = {
        "strict_json_schema": True,
        "reasoning_effort": "low",
        "max_completion_tokens": 2048,
        "input": {"available_tools": ["read_file", "check_port"]},
        "tool_parameter_schema": {
            "read_file": {"path": "string", "max_bytes": "integer"},
            "check_port": {"port": "integer", "host": "string"},
        },
    }
    provider = VLLMProvider()

    class _Gate:
        def acquire(self):
            pass

    provider._cerebras_gate = _Gate()
    provider._model = "gpt-oss-120b"
    provider.generate_structured("system", "user", ExplorerOutput, metadata=metadata)

    request_format = captured["response_format"]
    assert request_format["type"] == "json_schema"
    assert request_format["json_schema"]["strict"] is True
    schema = request_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    check_port = next(branch for branch in schema["properties"]["tool_request"]["anyOf"]
                      if branch["properties"]["tool"]["enum"] == ["check_port"])
    assert set(check_port["properties"]["parameters"]["properties"]) == {"port", "host"}
    assert set(check_port["properties"]["parameters"]["required"]) == {"port", "host"}
    assert check_port["properties"]["parameters"]["additionalProperties"] is False
    assert captured["max_completion_tokens"] == 2048
    assert captured["reasoning_effort"] == "low"
    assert "JSON Schema" not in captured["messages"][0]["content"]


def test_incomplete_strict_response_reports_finish_reason_without_repair(monkeypatch, vllm_env):
    def fake_post(url, json, timeout, headers=None):  # noqa: A002
        return _FakeResponse({"choices": [{"message": {"content": '{"tool":"start_process","parameters":{'},
                                   "finish_reason": "length"}], "usage": {"completion_tokens": 1024}})

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)
    with pytest.raises(LLMError, match="finish_reason=length"):
        VLLMProvider().generate_structured(
            "s", "u", ExplorerOutput,
            metadata={"strict_json_schema": True, "input": {"available_tools": ["start_process"]},
                      "tool_parameter_schema": {"start_process": {"command": "string"}}},
        )


def test_http_failure_raises_llm_error(monkeypatch, vllm_env):
    def fake_post(url, json, timeout, headers=None):  # noqa: A002
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)
    with pytest.raises(LLMError):
        VLLMProvider().generate_structured("s", "u", ExplorerOutput)


def test_invalid_json_raises_llm_error(monkeypatch, vllm_env):
    def fake_post(url, json, timeout, headers=None):  # noqa: A002
        return _FakeResponse({"choices": [{"message": {"content": "not json"}}]})

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)
    with pytest.raises(LLMError):
        VLLMProvider().generate_structured("s", "u", ExplorerOutput)


def test_full_flow_through_explorer_agent(monkeypatch, vllm_env, python_project_explorer_input):
    """Agent -> LLMProvider -> VLLMProvider -> HTTP -> JSON -> pydantic validation."""
    valid = _explorer_output_dict()
    valid["investigation_id"] = python_project_explorer_input.investigation_id
    valid["node_id"] = python_project_explorer_input.current_node.node_id

    def fake_post(url, json, timeout, headers=None):  # noqa: A002
        return _FakeResponse(_content(valid))

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)

    output = ExplorerAgent(VLLMProvider()).investigate(python_project_explorer_input)
    assert output.node_id == python_project_explorer_input.current_node.node_id


def test_non_strict_mode_honours_completion_budget_and_reasoning(monkeypatch, vllm_env):
    """Regression for the Verifier HTTP 422: in json_object (non-strict) mode the
    caller's max_completion_tokens was ignored (pinned at 1024) and reasoning_effort
    was dropped, so a reasoning model truncated the assessment into invalid JSON.
    Both must now be honoured in non-strict mode."""
    import os
    captured = {}

    def fake_post(url, json, timeout, headers=None):  # noqa: A002
        captured["json"] = json
        return _FakeResponse(_content(_explorer_output_dict()))

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)
    # Force the Cerebras gate on so reasoning_effort is eligible to be sent.
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "https://api.cerebras.ai")
    monkeypatch.setenv("WIZARD_LLM_MODEL", "gpt-oss-120b")

    provider = VLLMProvider()
    provider.generate_structured(
        "sys", "user", ExplorerOutput,
        metadata={"max_completion_tokens": 3000, "reasoning_effort": "low"},
    )
    assert captured["json"]["response_format"]["type"] == "json_object"
    assert captured["json"]["max_completion_tokens"] == 3000
    assert captured["json"].get("reasoning_effort") == "low"
