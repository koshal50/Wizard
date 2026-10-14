"""Metadata, lifecycle, durable retry, profile isolation, and SSE tests."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from wizard_kernel.api.app import create_app
from wizard_kernel.api.routes_usage import local_usage, usage_stream
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.storage.usage import UsageStore


def event(event_id="e1", **changes):
    return {
        "event_id": event_id,
        "provider": "fixture",
        "model": "fixture",
        "agent": "explorer",
        "provider_request_id": event_id,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "usage_source": "provider-reported",
        "accuracy": "exact",
        "created_at": datetime.now(UTC).isoformat(),
        **changes,
    }


def inv(run_id="inv_test", command="investigate"):
    return SimpleNamespace(
        id=run_id,
        intent=command,
        state=LifecycleState.planning,
        started_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class Database:
    def __init__(self):
        self.jobs = []
        self.fail = False

    def persist(self, job):
        if self.fail:
            raise RuntimeError("secret connection string must not be logged")
        self.jobs.append(job)

    def close(self):
        pass


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    result = UsageStore()
    result.database = Database()
    return result


@pytest.mark.parametrize("command", ["investigate", "verify", "report", "explain"])
def test_four_commands_multiple_calls_and_duplicate_delivery(store, command):
    run = inv(command=command)
    store.begin(run)
    with store.operation(run):
        store.response(SimpleNamespace(json=lambda: {"usage_events": [event(), event("e2")]}))
        store.response(SimpleNamespace(json=lambda: {"usage_events": [event()]}))
    store.flush()
    jobs = store.database.jobs
    assert all(j["run"]["command"] == command for j in jobs)
    assert jobs[-1]["run"]["pending_requests"] == 0
    assert sum(len(j["events"]) for j in jobs) == 3
    # Database idempotency is tested separately against PostgreSQL.
    assert not list(store.spool.glob("*.json"))


def test_persistence_failure_is_durable_observable_and_recoverable(store, caplog):
    store.begin(inv())
    store.database.fail = True
    store.flush()
    assert store.health()["persistence_pending"]
    assert store.error
    assert "secret connection" not in caplog.text
    restarted = UsageStore()
    assert restarted.profile_id == store.profile_id
    assert restarted.session_id == store.session_id
    restarted.database = Database()
    restarted.flush()
    assert len(restarted.database.jobs) == 1
    assert not restarted.health()["persistence_pending"]


def test_direct_runtime_provider_uses_existing_usage_spool(store):
    run = inv(command="verify")
    with store.operation(run):
        store.provider_response(SimpleNamespace(headers={"x-request-id": "native-request"},
            json=lambda: {"usage": {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42}}),
            "explorer", "gpt-oss-120b")
        store.provider_response(None, "verifier", "gpt-oss-120b")
    store.flush()
    events = [event for job in store.database.jobs for event in job["events"]]
    assert len(events) == 2
    successful = next(e for e in events if e["provider_request_id"] == "native-request")
    assert successful["total_tokens"] == 42 and successful["accuracy"] == "exact"
    assert successful["agent"] == "explorer"
    unavailable = next(e for e in events if e["agent"] == "verifier")
    assert unavailable["usage_source"] == "unavailable" and unavailable["total_tokens"] is None


@pytest.mark.parametrize("state", [LifecycleState.failed, LifecycleState.cancelled])
def test_failed_or_cancelled_run_retains_late_usage(store, state):
    run = inv()
    store.begin(run)
    with store.operation(run):
        run.state = state
        store.state(run)
        store.response(SimpleNamespace(json=lambda: {"usage_events": [event()]}))
    store.flush()
    assert store.database.jobs[-1]["run"]["status"] == state.value
    assert any(job["events"] for job in store.database.jobs)


def test_zero_model_calls_and_missing_sidecar_metadata(store):
    run = inv()
    store.begin(run)
    with store.operation(run):
        store.response(SimpleNamespace(json=lambda: {"usage_events": []}))
    assert not store.runs[run.id]["incomplete"]
    with store.operation(run):
        store.response(SimpleNamespace(json=dict))
    assert store.runs[run.id]["incomplete"]


def test_invalid_event_does_not_discard_valid_usage(store):
    run = inv()
    store.begin(run)
    with store.operation(run):
        store.response(
            SimpleNamespace(json=lambda: {"usage_events": [event(), event("bad", input_tokens=-1)]})
        )
    store.flush()
    assert len([e for j in store.database.jobs for e in j["events"]]) == 1
    assert store.runs[run.id]["incomplete"]


def snapshot(**changes):
    return {
        "run_id": "inv_test",
        "session_id": "session",
        "profile_id": "local",
        "command": "report",
        "status": "completed",
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "revision": 42,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "llm_calls": 1,
        "pending_requests": 0,
        **changes,
    }


def test_client(app, host="127.0.0.1"):
    async def scoped(scope, receive, send):
        scope = {**scope, "client": (host, 1234)}
        await app(scope, receive, send)

    return TestClient(scoped)


test_client.__test__ = False


def test_completed_stream_and_reconnect_always_return_latest_snapshot(store):
    app = create_app()
    store.database.run = lambda profile, run: snapshot() if run == "inv_test" else None
    app.dependency_overrides[local_usage] = lambda: store
    client = test_client(app)
    for headers in ({}, {"Last-Event-ID": "42"}, {"Last-Event-ID": "0"}):
        response = client.get("/v1/investigations/inv_test/usage/stream", headers=headers)
        assert "id: 42" in response.text
        assert "event: complete" in response.text
        assert json.loads(response.text.split("data: ")[1].split("\n")[0])["total_tokens"] == 15
    assert client.get("/v1/investigations/foreign/usage").status_code == 404


def test_disconnect_stops_generator_without_writing_or_model_calls(store):
    class Request:
        async def is_disconnected(self):
            return True

    async def collect():
        return [part async for part in usage_stream(Request(), store, "inv_test", snapshot())]

    assert asyncio.run(collect()) == []
    assert store.database.jobs == []


def test_remote_usage_access_is_denied_and_profile_is_server_owned(monkeypatch, store):
    monkeypatch.setattr("wizard_kernel.api.routes_usage.get_usage", lambda: store)
    store.database.run = lambda profile, run: snapshot(profile_id=profile)
    app = create_app()
    remote = test_client(app, "192.0.2.10")
    assert remote.get("/v1/usage").status_code == 403
    local = test_client(app)
    response = local.get("/v1/investigations/inv_test/usage?profile_id=foreign")
    assert response.json()["profile_id"] == store.profile_id


def test_unconfigured_database_returns_clear_503(monkeypatch, store):
    store.database = None
    monkeypatch.setattr("wizard_kernel.api.routes_usage.get_usage", lambda: store)
    response = test_client(create_app()).get("/v1/usage")
    assert response.status_code == 503


def test_usage_endpoint_retries_failed_storage_startup(monkeypatch, store):
    database = store.database
    database.run = lambda profile, run: snapshot(profile_id=profile)
    store.database = None
    store.error = "PostgreSQL usage configuration, schema, or connection unavailable"

    def restart():
        store.database = database
        store.error = None

    monkeypatch.setattr(store, "start", restart)
    monkeypatch.setattr("wizard_kernel.api.routes_usage.get_usage", lambda: store)
    response = test_client(create_app()).get("/v1/investigations/inv_test/usage")
    assert response.status_code == 200
    assert response.json()["total_tokens"] == 15
    assert response.json()["persistence_error"] is None


def test_restart_recovery_clears_temporary_failure(store):
    store.error = "Usage restart reconciliation is awaiting PostgreSQL"
    store.database.recover = lambda *args: store.stop.set()
    store._worker()
    assert store.error is None
    assert not store.recovery_pending


def test_failed_pool_initialization_can_retry_without_duplicate_pool(monkeypatch, store):
    import wizard_kernel.storage.usage_db as db

    store.database = None
    calls = []

    def connect(url):
        calls.append(url)
        if len(calls) == 1:
            raise RuntimeError("temporary startup failure")
        database = Database()
        database.recover = lambda *args: None
        return database

    monkeypatch.setattr(db, "database_url", lambda: "fixture")
    monkeypatch.setattr(db, "UsageDatabase", connect)
    store.start()
    assert store.database is None and store.error
    store.start()
    assert len(calls) == 1  # bounded retry backoff
    store.retry_at = 0
    try:
        store.start()
        store.start()
        assert len(calls) == 2
        assert store.database is not None and store.error is None
    finally:
        store.close()


def test_active_sse_publishes_changed_snapshots_then_reconciles(monkeypatch, store):
    import wizard_kernel.api.routes_usage as routes

    values = iter(
        [
            snapshot(total_tokens=12, revision=2, finished_at=None),
            snapshot(total_tokens=15, revision=3),
        ]
    )
    monkeypatch.setattr(routes, "read_run", lambda *args: next(values))

    async def no_delay(seconds):
        pass

    monkeypatch.setattr(routes.asyncio, "sleep", no_delay)

    class Request:
        async def is_disconnected(self):
            return False

    async def collect():
        return [
            part
            async for part in usage_stream(
                Request(), store, "inv_test", snapshot(total_tokens=0, revision=1, finished_at=None)
            )
        ]

    messages = asyncio.run(collect())
    assert len(messages) == 4
    totals = [
        json.loads(message.split("data: ")[1].split("\n")[0])["total_tokens"]
        for message in messages[:-1]
    ]
    assert totals == [0, 12, 15]
    assert "event: complete" in messages[-1]


def test_spool_failure_does_not_throw_or_claim_complete(store, monkeypatch):
    monkeypatch.setattr(store, "_write", lambda *args: (_ for _ in ()).throw(OSError("read-only")))
    store.begin(inv())
    assert store.health()["accounting_incomplete"]


def test_direct_runtime_database_configuration_reads_root_dotenv(monkeypatch, tmp_path):
    from wizard_kernel.storage import usage_db

    engine = tmp_path / "wizard-runtime-engine"
    module = engine / "src" / "wizard_kernel" / "storage" / "usage_db.py"
    module.parent.mkdir(parents=True)
    (tmp_path / ".env").write_text("Wizard_DATABASE_URL=postgresql://fixture\n", encoding="utf-8")
    monkeypatch.delenv("WIZARD_DATABASE_URL", raising=False)
    monkeypatch.setattr(usage_db, "__file__", str(module))
    monkeypatch.chdir(engine)
    assert usage_db.database_url() == "postgresql://fixture"
    monkeypatch.setenv("WIZARD_DATABASE_URL", "postgresql://explicit")
    assert usage_db.database_url() == "postgresql://explicit"
    monkeypatch.setenv("WIZARD_DATABASE_URL", "")
    assert usage_db.database_url() is None


def test_selected_status_run_is_authorized_and_includes_named_intent(store, monkeypatch):
    from wizard_kernel.storage import fs_store

    store.database.overall = lambda profile, session: {
        "scope": "local-profile",
        "profile_id": profile,
        "totals": {},
        "by_command": {},
        "current_run": snapshot(run_id="other"),
    }
    store.database.run = lambda profile, run_id: snapshot() if run_id == "inv_test" else None
    fs_store.write(
        "inv_test", "meta.json", {"targets": ["architecture", "https://secret:password@host/"]}
    )
    monkeypatch.setattr("wizard_kernel.api.routes_usage.get_usage", lambda: store)
    client = test_client(create_app())
    result = client.get("/v1/usage?run_id=inv_test")
    assert result.status_code == 200
    assert result.json()["current_run"]["run_id"] == "inv_test"
    assert result.json()["current_run"]["intent"] == "architecture"
    assert "password" not in result.text
    assert client.get("/v1/usage?run_id=foreign").status_code == 404
