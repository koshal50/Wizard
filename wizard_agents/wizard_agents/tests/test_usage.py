from concurrent.futures import ThreadPoolExecutor

import pytest
from app.contracts.explorer import ExplorerOutput
from app.llm.base import LLMError
from app.llm.usage import collect_usage, normalize_usage, record_usage
from app.llm.vllm_provider import VLLMProvider


@pytest.mark.parametrize(
    "usage, expected",
    [
        (
            {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            (10, 4, 14, "exact"),
        ),
        ({"input_tokens": 10, "output_tokens": 4}, (10, 4, 14, "exact")),
        ({"total_tokens": 14}, (None, None, 14, "incomplete")),
        ({"completion_tokens": 4}, (None, 4, None, "incomplete")),
        (
            {"prompt_tokens": -1, "completion_tokens": True},
            (None, None, None, "incomplete"),
        ),
        ({"prompt_tokens": 0, "completion_tokens": 0}, (0, 0, 0, "exact")),
    ],
)
def test_normalization(usage, expected):
    result = normalize_usage({"usage": usage})
    assert (
        tuple(
            result[k]
            for k in ("input_tokens", "output_tokens", "total_tokens", "accuracy")
        )
        == expected
    )


def test_collectors_are_isolated_and_restore_nested_context():
    def worker(model):
        with collect_usage() as events:
            record_usage(None, provider="fixture", model=model)
            with collect_usage() as nested:
                record_usage(None, provider="fixture", model="nested")
            assert len(nested) == 1
            record_usage(None, provider="fixture", model=model)
        return events

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(worker, ["first", "second"]))
    assert [e["model"] for e in first] == ["first", "first"]
    assert [e["model"] for e in second] == ["second", "second"]
    assert len({e["event_id"] for e in first + second}) == 4


def test_invalid_model_response_retains_authoritative_usage(monkeypatch):
    class Response:
        status_code = 200

        def __init__(self):
            self.headers = {"x-request-id": "provider-123"}

        def json(self):
            return {
                "choices": [{"message": {"content": "invalid"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            }

        def raise_for_status(self):
            pass

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", lambda *a, **kw: Response())
    with collect_usage() as events, pytest.raises(LLMError):
        VLLMProvider(
            model="fixture", base_url="http://localhost:8000"
        ).generate_structured("secret prompt", "source code", ExplorerOutput)
    assert len(events) == 1
    assert events[0]["total_tokens"] == 28
    assert events[0]["provider_request_id"] == "provider-123"
    assert "secret prompt" not in str(events)
    assert "source code" not in str(events)


def test_retry_records_each_actual_request(monkeypatch):
    class Gate:
        def acquire(self, **kwargs):
            pass

        def defer(self, wait):
            pass

    class Response:
        def __init__(self, status):
            self.status_code = status
            self.headers = {"retry-after": "0"}

        def json(self):
            return {
                "choices": [{"message": {"content": "invalid"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }

        def raise_for_status(self):
            pass

    responses = iter([Response(429), Response(200)])
    monkeypatch.setattr(
        "app.llm.vllm_provider.httpx.post", lambda *a, **kw: next(responses)
    )
    provider = VLLMProvider(model="fixture", base_url="http://localhost:8000")
    provider._cerebras_gate = Gate()
    with collect_usage() as events, pytest.raises(LLMError):
        provider.generate_structured("s", "u", ExplorerOutput)
    assert len(events) == 2
    assert sum(e["total_tokens"] for e in events) == 24


def test_mock_and_no_requests_produce_no_usage():
    with collect_usage() as events:
        pass
    assert events == []


def test_runtime_error_reply_includes_usage_only_when_requested(monkeypatch):
    from app.api.deps import get_provider
    from app.api.main import app
    from fastapi.testclient import TestClient

    from tests.test_runtime_adapter import _kernel_explorer_packet

    class Response:
        status_code = 200

        def __init__(self):
            self.headers = {"x-request-id": "request-usage"}

        def json(self):
            return {
                "choices": [{"message": {"content": "invalid"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

        def raise_for_status(self):
            pass

    monkeypatch.setattr("app.llm.vllm_provider.httpx.post", lambda *a, **kw: Response())
    app.dependency_overrides[get_provider] = lambda: VLLMProvider(
        model="fixture", base_url="http://localhost"
    )
    try:
        client = TestClient(app)
        packet = _kernel_explorer_packet()
        original = client.post("/agent/explorer", json=packet)
        assert original.status_code == 422
        assert "usage_events" not in original.json()
        tracked = client.post("/agent/explorer", json={**packet, "_usage": True})
        assert tracked.status_code == 422
        assert tracked.json()["usage_events"][0]["total_tokens"] == 15
    finally:
        app.dependency_overrides.clear()
