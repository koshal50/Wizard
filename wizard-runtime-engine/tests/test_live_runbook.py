"""Local usage notifications and read-only report projections; no providers."""
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.storage.usage import UsageStore
from wizard_kernel.api.routes_usage import read_run
from wizard_kernel.control.runbook import project, markdown, html_report, persist


def investigation():
    return SimpleNamespace(id="inv_live_report", intent="verify", targets=["runtime"],
                           question="Check application", state=LifecycleState.planning,
                           started_at=datetime.now(UTC), updated_at=datetime.now(UTC))


def test_usage_notifies_without_database_and_survives_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    store = UsageStore()
    inv = investigation()
    store.begin(inv)
    revision = store.runs[inv.id]["revision"]
    with ThreadPoolExecutor() as pool:
        waiting = pool.submit(store.wait_for_revision, inv.id, revision, 1)
        with store.operation(inv):
            store.provider_response(SimpleNamespace(headers={}, json=lambda: {"usage": {
                "prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}}), "explorer", "fixture")
        waiting.result(timeout=2)
    live = read_run(store, inv.id)
    assert live["total_tokens"] == 23 and live["llm_calls"] == 1
    assert live["revision"] != revision and live["pending_requests"] == 0
    assert live["persistence_pending"] and not live["incomplete"]
    assert "seen_events" not in live
    restarted = UsageStore()
    restarted.begin(inv)
    assert read_run(restarted, inv.id)["total_tokens"] == 23
    assert restarted.snapshot(inv.id, "another-profile") is None


def test_usage_duplicate_event_is_not_counted_twice(monkeypatch, tmp_path):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    store = UsageStore()
    inv = investigation()
    event = {"event_id": "same", "provider": "fixture", "model": "fixture", "input_tokens": 2,
             "output_tokens": 1, "total_tokens": 3, "usage_source": "provider-reported", "accuracy": "exact",
             "created_at": datetime.now(UTC).isoformat()}
    with store.operation(inv):
        for _ in range(2):
            store.response(SimpleNamespace(json=lambda: {"usage_events": [event]}))
    assert read_run(store, inv.id)["total_tokens"] == 3
    assert read_run(store, inv.id)["llm_calls"] == 1


def state():
    return {"checks": [{"id": "web", "description": "Application loads", "assertions": []},
                       {"id": "missing", "description": "Sign in", "assertions": []}],
            "results": {"web": {"status": "passed", "assertions": [{"actual": "Observed welcome page",
                        "observation_id": "obs_actual", "verdict": "passed"}]}},
            "executions": [{"id": "execution", "check_id": "web", "tool": "start_process",
                            "parameters": {"command": "python server.py", "cwd": "service", "password": "never-export-this"},
                            "state": "observed", "success": True, "observation_id": "obs_actual"}],
            "cleanup": "stopped owned processes"}


def test_report_is_projection_with_provenance_and_no_fake_success():
    original = state()
    before = json.dumps(original, sort_keys=True)
    data = project(investigation(), original)
    assert [c["status"] for c in data["checks"]] == ["VERIFIED", "UNVERIFIED"]
    assert data["steps"][0]["observation_id"] == "obs_actual"
    report = markdown(data)
    assert "python server.py" in report and "Working directory: `service`" in report
    assert "Observed welcome page" in report
    assert "never-export-this" not in json.dumps(data)
    assert json.dumps(original, sort_keys=True) == before


def test_offline_report_escapes_observations_and_contains_real_diagram(monkeypatch, tmp_path):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    inv = investigation()
    original = state()
    original["checks"][0]["description"] = '<script>alert("bad")</script>'
    data = project(inv, original)
    output = html_report(data)
    assert "<svg" in output and "obs_actual" in output
    assert "<script>" not in output and "&lt;script&gt;" in output
    persist(inv, original)
    from wizard_kernel.storage import fs_store
    assert fs_store.read(inv.id, "runbook.json")["schema_version"] == 1
    assert fs_store.read_text(inv.id, "runbook.html") == output


def test_report_api_serves_live_structured_report_and_safe_offline_html(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from wizard_kernel.api.app import create_app
    from wizard_kernel.api.deps import get_manager
    from wizard_kernel.storage import fs_store
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    inv = investigation()
    data = persist(inv, state())
    fs_store.write_text(inv.id, "verification_report.md", markdown(data))
    app = create_app()
    app.dependency_overrides[get_manager] = lambda: SimpleNamespace(get=lambda identifier: inv if identifier == inv.id else None)
    client = TestClient(app)
    response = client.get(f"/v1/investigations/{inv.id}/report")
    assert response.status_code == 200
    assert response.json()["runbook"]["steps"][0]["observation_id"] == "obs_actual"
    offline = client.get(f"/v1/investigations/{inv.id}/report/html")
    assert offline.status_code == 200 and "<svg" in offline.text
    assert "default-src 'none'" in offline.headers["content-security-policy"]
    assert client.get("/v1/investigations/missing/report/html").status_code == 404
