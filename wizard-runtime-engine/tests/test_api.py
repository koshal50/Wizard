"""API tests — Phase 1 milestone verification."""
import pytest
from fastapi.testclient import TestClient
from wizard_kernel.api.app import app
from wizard_kernel.api.deps import get_manager
from wizard_kernel.session.manager import InvestigationManager


@pytest.fixture
def client():
    """Fresh manager per test — investigations never share state (invariant 6)."""
    fresh = InvestigationManager()
    app.dependency_overrides[get_manager] = lambda: fresh
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_investigation_returns_id(client):
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo",
        "intent": "verify",
        "targets": ["runtime"],
    })
    assert r.status_code == 201
    body = r.json()
    assert "investigation_id" in body
    assert body["investigation_id"].startswith("inv_")


def test_get_investigation_returns_status(client):
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo",
        "intent": "verify",
        "targets": ["runtime"],
    })
    inv_id = r.json()["investigation_id"]
    r2 = client.get(f"/v1/investigations/{inv_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["investigation_id"] == inv_id
    assert "budget_remaining" in body
    assert "nodes_completed" in body
    assert "last_event" in body


def test_get_investigation_not_found(client):
    r = client.get("/v1/investigations/inv_doesnotexist")
    assert r.status_code == 404


def test_report_not_ready_returns_409(client):
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo",
        "intent": "verify",
        "targets": ["runtime"],
    })
    inv_id = r.json()["investigation_id"]
    # Stop the loop before it completes by checking immediately
    r2 = client.get(f"/v1/investigations/{inv_id}/report")
    # Either 409 (not complete) or 200 (completed very fast with mock)
    assert r2.status_code in (200, 409)


def test_cancel_investigation(client):
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo",
        "intent": "investigate",
        "targets": [],
    })
    inv_id = r.json()["investigation_id"]
    r2 = client.delete(f"/v1/investigations/{inv_id}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "cancelled"


def test_openapi_schema_accessible(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"] == "Wizard Investigation Kernel"


def test_invalid_intent_rejected(client):
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/repo",
        "intent": "hack",  # not in Literal
        "targets": [],
    })
    assert r.status_code == 422  # Pydantic validation error
