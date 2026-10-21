"""Conversation transport uses the shared provider and metadata-only accounting."""

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from wizard_kernel.api.account_auth import authenticated_account_id
from wizard_kernel.api.app import create_app
from wizard_kernel.storage.usage import get_usage


def packet():
    return {"conversation_id": str(uuid4()), "session_id": str(uuid4()),
            "messages": [{"role": "user", "content": "only the branch command"}]}


def setup_provider(monkeypatch, content="git branch --show-current", usage=None, failure=None):
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://provider.test")
    monkeypatch.setenv("WIZARD_LLM_MODEL", "configured-model")
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        if failure:
            raise failure
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"text": content})}}], "usage": usage}, headers={"x-request-id": str(uuid4())})
    monkeypatch.setattr("wizard_kernel.ports.model.httpx.post", post)
    return calls


def test_actual_tokens_use_separate_btw_identity_and_never_store_messages(monkeypatch, tmp_path):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    calls = setup_provider(monkeypatch, usage={"prompt_tokens": 13, "completion_tokens": 7, "total_tokens": 20})
    app = create_app()
    app.dependency_overrides[authenticated_account_id] = lambda: "account-owner"
    request = packet()
    with TestClient(app) as client:
        response = client.post("/v1/btw", json=request)
    assert response.status_code == 200
    assert response.json() == {"conversation_id": request["conversation_id"], "text": "git branch --show-current"}
    assert calls[0]["model"] == "configured-model"
    assert "only the branch command" in calls[0]["messages"][1]["content"]
    jobs = [json.loads(p.read_text()) for p in (tmp_path / "usage/pending").glob("*.json")]
    events = [e for job in jobs for e in job["events"]]
    assert len(events) == 1
    assert events[0]["input_tokens"] == 13 and events[0]["output_tokens"] == 7
    assert events[0]["total_tokens"] == 20 and events[0]["usage_source"] == "provider-reported"
    assert all(j["run"]["command"] == "btw" and j["run"]["profile_id"] == "account:account-owner" for j in jobs)
    assert all(j["run"]["run_id"].startswith("btw-" + request["conversation_id"].replace("-", "")) for j in jobs)
    for file in tmp_path.rglob("*"):
        if file.is_file():
            data = file.read_text()
            assert "only the branch command" not in data and "git branch" not in data
    assert not list(tmp_path.glob("investigations/*"))


@pytest.mark.parametrize("failure,content", [(httpx.ReadTimeout("timeout"), "unused"), (None, " ")])
def test_provider_failure_and_empty_response_are_safe_and_accounted(monkeypatch, failure, content):
    setup_provider(monkeypatch, content=content, failure=failure)
    with TestClient(create_app()) as client:
        response = client.post("/v1/btw", json=packet())
        assert response.status_code == 502
        runs = get_usage().runs
        assert len(runs) == 1 and next(iter(runs.values()))["status"] == "failed"


def test_missing_usage_is_unknown_not_estimated(monkeypatch):
    setup_provider(monkeypatch, usage=None)
    with TestClient(create_app()) as client:
        assert client.post("/v1/btw", json=packet()).status_code == 200
        events = [e for p in get_usage().spool.glob("*.json") for e in json.loads(p.read_text())["events"]]
        assert events[-1]["total_tokens"] is None
        assert events[-1]["accuracy"] == "incomplete"


def test_empty_question_rejected_before_provider(monkeypatch):
    calls = setup_provider(monkeypatch)
    request = packet()
    request["messages"][0]["content"] = "   "
    with TestClient(create_app()) as client:
        assert client.post("/v1/btw", json=request).status_code == 422
    assert not calls
