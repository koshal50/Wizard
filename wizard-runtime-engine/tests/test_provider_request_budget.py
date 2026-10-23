"""Provider request contracts, tested without network or model calls."""
import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from wizard_kernel.ports.model import ModelPolicy, ModelFailure
from wizard_kernel.contracts.verification import ArchitectureReport, ARCHITECTURE_AREAS


def test_architecture_report_has_bounded_distinct_output_limit(monkeypatch):
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://provider.test")
    answer = ArchitectureReport(findings=[{"area": area, "summary": "Insufficient evidence", "blocker": "No source observed"} for area in ARCHITECTURE_AREAS])
    def respond(url, **kwargs):
        assert kwargs["json"]["max_completion_tokens"] == 3072
        assert kwargs["json"]["response_format"]["json_schema"]["strict"]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": answer.model_dump_json()}}]})
    monkeypatch.setattr(httpx, "post", respond)
    result = ModelPolicy().request("explorer", {"architecture_synthesis": True, "repository_evidence": []}, ArchitectureReport)
    assert len(result.findings) == 6
class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str


def test_protected_request_over_31000_characters_reaches_transport(monkeypatch, tmp_path):
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "https://api.cerebras.ai/v1")
    monkeypatch.setenv("WIZARD_CEREBRAS_GATE_DB", str(tmp_path / "gate.sqlite"))
    calls = []
    def respond(url, **kwargs):
        payload = kwargs["json"]
        calls.append(payload)
        assert len(payload["messages"][1]["content"]) > 31000
        assert payload["response_format"]["json_schema"]["strict"]
        assert payload["max_completion_tokens"] == 1024
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"tool":"read_file"}'}}]})
    monkeypatch.setattr(httpx, "post", respond)
    policy = ModelPolicy()
    assert policy.gate is not None
    result = policy.request("explorer", {"current_goal": "x" * 31313}, Decision)
    assert result.tool == "read_file"
    assert len(calls) == 1


def test_request_still_respects_explicit_context_limit(monkeypatch):
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://provider.test")
    def forbidden(*args, **kwargs):
        pytest.fail("Oversized request must not reach transport")
    monkeypatch.setattr(httpx, "post", forbidden)
    with pytest.raises(ModelFailure, match="Protected request size"):
        ModelPolicy().request("explorer", {"current_goal": "x" * 61000}, Decision)
