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

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self) -> dict:
        return self._payload


def _content(obj: dict) -> dict:
    """Build an OpenAI-compatible chat.completions payload."""
    return {"choices": [{"message": {"content": json.dumps(obj)}}]}


@pytest.fixture()
def vllm_env(monkeypatch):
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://vllm.local:8000")
    monkeypatch.setenv("WIZARD_LLM_MODEL", "test/open-model")


def _explorer_output_dict() -> dict:
    return ExplorerOutput(
        investigation_id="inv-1",
        node_id="n1",
        purpose="p",
        reasoning="r",
        selected_tool="read_file",
        parameters={"path": "."},
        execution_steps=[
            {"step_number": 1, "description": "read", "tool": "read_file", "parameters": {"path": "."}}
        ],
        expected_observation="obs",
        success_condition="ok",
        failure_condition="fail",
    ).model_dump(mode="json")


def test_requires_model(monkeypatch):
    monkeypatch.delenv("WIZARD_LLM_MODEL", raising=False)
    with pytest.raises(LLMError):
        VLLMProvider()


def test_generate_structured_success(monkeypatch, vllm_env):
    captured = {}

    def fake_post(url, json, timeout):  # noqa: A002 - match httpx signature
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
    # schema is injected into the system message
    assert "JSON Schema" in captured["json"]["messages"][0]["content"]


def test_http_failure_raises_llm_error(monkeypatch, vllm_env):
    def fake_post(url, json, timeout):  # noqa: A002
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)
    with pytest.raises(LLMError):
        VLLMProvider().generate_structured("s", "u", ExplorerOutput)


def test_invalid_json_raises_llm_error(monkeypatch, vllm_env):
    def fake_post(url, json, timeout):  # noqa: A002
        return _FakeResponse({"choices": [{"message": {"content": "not json"}}]})

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)
    with pytest.raises(LLMError):
        VLLMProvider().generate_structured("s", "u", ExplorerOutput)


def test_full_flow_through_explorer_agent(monkeypatch, vllm_env, python_project_explorer_input):
    """Agent -> LLMProvider -> VLLMProvider -> HTTP -> JSON -> pydantic validation."""
    valid = _explorer_output_dict()
    valid["investigation_id"] = python_project_explorer_input.investigation_id
    valid["node_id"] = python_project_explorer_input.current_node.node_id

    def fake_post(url, json, timeout):  # noqa: A002
        return _FakeResponse(_content(valid))

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", fake_post)

    output = ExplorerAgent(VLLMProvider()).investigate(python_project_explorer_input)
    assert output.node_id == python_project_explorer_input.current_node.node_id
