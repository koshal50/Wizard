from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api import deps
from app.llm.mock_provider import MockLLMProvider


@pytest.fixture(autouse=True)
def _use_mock_provider():
    """Force the API to use MockLLMProvider regardless of env vars, and
    reset FastAPI dependency overrides between tests."""
    app.dependency_overrides[deps.get_provider] = lambda: MockLLMProvider()
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_health_endpoint(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_explorer_endpoint_success(client: TestClient, python_project_explorer_input):
    resp = client.post(
        "/explorer/investigate", json=python_project_explorer_input.model_dump(mode="json")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["node_id"] == python_project_explorer_input.current_node.node_id
    assert "selected_tool" in body


def test_explorer_endpoint_validation_error(client: TestClient):
    resp = client.post("/explorer/investigate", json={"investigation_id": "inv-1"})
    assert resp.status_code == 422


def test_verification_endpoint_success(client: TestClient, verification_input_multi):
    resp = client.post(
        "/verification/verify", json=verification_input_multi.model_dump(mode="json")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["investigation_id"] == verification_input_multi.investigation_id
    assert "report_markdown" in body


def test_verification_endpoint_validation_error(client: TestClient):
    resp = client.post("/verification/verify", json={"investigation_id": "inv-1", "claims": []})
    assert resp.status_code == 422
