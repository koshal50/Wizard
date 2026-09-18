"""API tests — Phase 1 milestone verification."""
import pytest
from fastapi.testclient import TestClient
from wizard_kernel.api.app import app
from wizard_kernel.api.deps import get_manager
from wizard_kernel.contracts.status import LifecycleState, is_terminal
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store


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
    """The cancel reports the state the engine ends in — and a GET agrees.

    This used to assert `status == "cancelled"` unconditionally, which the route
    answered even when the cancel had been refused (terminal states are
    absorbing, so an investigation that already failed or completed keeps its
    state). The response and the next GET then contradicted each other. What is
    guaranteed is that the two agree, and that the investigation is terminal.
    The won-cancel and lost-cancel cases are asserted deterministically in
    tests/test_cancellation.py, where no run loop is racing the assertion.
    """
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo",
        "intent": "investigate",
        "targets": [],
    })
    inv_id = r.json()["investigation_id"]
    r2 = client.delete(f"/v1/investigations/{inv_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] in ("completed", "failed", "cancelled")
    assert body["cancelled"] == (body["status"] == "cancelled")
    assert client.get(f"/v1/investigations/{inv_id}").json()["status"] == body["status"]


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


def test_status_says_whether_the_run_has_stopped(client):
    """The Runtime answers "are you done", so no client keeps its own state list.

    The CLI used to carry its own copy of the terminal states and went on polling
    forever once `incomplete` was added, because its copy still named only the
    three states that existed when it was written.
    """
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo", "intent": "verify", "targets": ["runtime"],
    })
    inv_id = r.json()["investigation_id"]
    body = client.get(f"/v1/investigations/{inv_id}").json()
    assert "is_terminal" in body
    # Whichever way the run went, the flag and the state have to agree.
    assert body["is_terminal"] is is_terminal(body["status"])


def test_every_terminal_state_is_recognised_as_terminal():
    """Including `incomplete` — the one addition that broke the client's copy."""
    for state in ("completed", "incomplete", "failed", "cancelled"):
        assert is_terminal(state), f"{state} is terminal"
    for state in ("created", "scanning", "planning", "investigation_loop", "reporting"):
        assert not is_terminal(state), f"{state} is not terminal"


def test_an_unknown_state_is_not_called_terminal():
    """Fail safe: a state this kernel does not know has not finished."""
    assert not is_terminal("teleported")


def test_the_report_is_served_whenever_it_exists_on_disk():
    """An `incomplete` run writes a report too, and it must be readable.

    The route used to gate on the state being `completed`, so a report sitting on
    disk was reported as "not ready" — the walk-away case where the caller is
    told there is nothing exactly when there is something.
    """
    manager = InvestigationManager()
    app.dependency_overrides[get_manager] = lambda: manager
    try:
        with TestClient(app, raise_server_exceptions=True) as c:
            r = c.post("/v1/investigations", json={
                "repository_path": "/tmp/test-repo", "intent": "verify", "targets": [],
            })
            inv_id = r.json()["investigation_id"]

            manager.update(inv_id, state=LifecycleState.incomplete,
                           last_event="the budget ran out; still open: Verify Runtime")
            fs_store.write_text(inv_id, "verification_report.md", "# Report\n\nopen goals")

            r2 = c.get(f"/v1/investigations/{inv_id}/report")
            assert r2.status_code == 200, r2.json()
            assert "open goals" in r2.json()["report_markdown"]
    finally:
        app.dependency_overrides.clear()
