"""Opt-in live PostgreSQL tests, confined to a unique temporary schema."""

import os
from datetime import UTC
from uuid import uuid4

import pytest

from wizard_kernel.storage.usage_db import UsageDatabase, migrate


@pytest.fixture
def database():
    url = os.environ.get("WIZARD_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set WIZARD_TEST_DATABASE_URL for isolated PostgreSQL integration tests")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    schema = "wizard_usage_test_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped_url = make_conninfo(url, options=f"-c search_path={schema}")
    try:
        migrate(scoped_url)
        migrate(scoped_url)
        db = UsageDatabase(scoped_url)
        yield db
        db.close()
    finally:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def job(run_id="r1", session="s1", profile="local", command="investigate", **event_changes):
    from datetime import datetime

    now = datetime.now(UTC).isoformat()
    return {
        "run": {
            "run_id": run_id,
            "session_id": session,
            "profile_id": profile,
            "command": command,
            "status": "completed",
            "started_at": now,
            "finished_at": now,
            "revision": 1,
            "pending_requests": 0,
            "incomplete": False,
        },
        "events": [
            {
                "event_id": run_id + "e",
                "provider": "fixture",
                "model": "fixture",
                "provider_request_id": run_id + "request",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "usage_source": "provider-reported",
                "accuracy": "exact",
                "created_at": now,
                **event_changes,
            }
        ],
    }


def test_persistence_aggregation_duplicates_sessions_and_profile_isolation(database):
    for i, command in enumerate(("investigate", "verify", "report", "explain")):
        value = job(f"r{i}", session=f"s{i % 2}", command=command)
        database.persist(value)
        database.persist(value)
        value["events"][0]["event_id"] += "duplicate"
        database.persist(value)
    database.persist(job("foreign", "foreign-session", "foreign"))
    overall = database.overall("local")
    assert overall["totals"]["total_tokens"] == 60
    assert overall["totals"]["llm_calls"] == 4
    assert len(overall["by_command"]) == 4
    assert database.overall("local", "s0")["totals"]["total_tokens"] == 30
    assert database.run("local", "r0")["total_tokens"] == 15
    assert database.run("local", "foreign") is None
    assert database.overall("empty")["totals"]["total_tokens"] == 0
    assert database.overall("local", "foreign-session")["totals"]["llm_calls"] == 0
    with pytest.raises(ValueError, match="ownership"):
        database.persist(job("unauthorized", "foreign-session", "local"))
    assert database.run("local", "unauthorized") is None


def test_btw_usage_is_separate_from_primary_run(database):
    database.persist(job("parent", session="primary", command="investigate"))
    database.persist(job("btw-turn", session="side", command="btw", input_tokens=3, output_tokens=2, total_tokens=5))
    database.persist(job("btw-turn", session="side", command="btw", input_tokens=3, output_tokens=2, total_tokens=5))
    assert database.run("local", "parent")["total_tokens"] == 15
    assert database.run("local", "btw-turn")["total_tokens"] == 5
    report = database.overall("local")
    assert report["totals"]["total_tokens"] == 20
    assert report["by_command"]["btw"]["total_tokens"] == 5
    assert report["by_command"]["investigate"]["total_tokens"] == 15


def test_authoritative_usage_replaces_provisional_without_double_counting(database):
    value = job(
        total_tokens=100,
        input_tokens=90,
        output_tokens=10,
        usage_source="estimated",
        accuracy="provisional",
    )
    database.persist(value)
    provisional = database.run("local", "r1")
    assert provisional["total_tokens"] == 0
    assert provisional["input_tokens"] == 0
    assert provisional["output_tokens"] == 0
    assert provisional["incomplete"]
    final = job()
    final["run"]["revision"] = 2
    database.persist(final)
    database.persist(value)
    result = database.run("local", "r1")
    assert result["total_tokens"] == 15
    assert result["llm_calls"] == 1
    assert not result["incomplete"]


def test_migration_is_additive_constraints_and_restart_recovery(database):
    with database.pool.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM information_schema.tables WHERE table_schema=current_schema()"
            ).fetchone()["n"]
            == 3
        )
    value = job()
    value["run"].update(status="running", finished_at=None, pending_requests=1)
    database.persist(value)
    database.recover("local")
    result = database.run("local", "r1")
    assert result["status"] == "incomplete"
    assert result["incomplete"]
    assert result["total_tokens"] == 15
    assert result["pending_requests"] == 0
    from psycopg.errors import CheckViolation

    with pytest.raises(CheckViolation):
        database.persist(job("bad", input_tokens=-1))


def test_reapplying_migration_preserves_existing_database_consumers(database):
    with database.pool.connection() as conn:
        conn.execute("CREATE TABLE existing_consumer_guard(value integer)")
        conn.execute("INSERT INTO existing_consumer_guard VALUES (42)")
    migrate(database.pool.conninfo)
    with database.pool.connection() as conn:
        assert conn.execute("SELECT value FROM existing_consumer_guard").fetchone()["value"] == 42


def test_existing_execution_workers_api_sse_and_all_commands(database, monkeypatch, tmp_path):
    import json
    import time
    from types import SimpleNamespace

    from wizard_kernel.api.app import create_app
    from wizard_kernel.api.routes_investigations import kernel_loop
    from wizard_kernel.contracts.status import LifecycleState
    from wizard_kernel.session.control import RunControl
    from wizard_kernel.storage.usage import capture_response, get_usage

    from .test_usage import test_client

    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    get_usage.cache_clear()
    store = get_usage()
    store.database = database
    # The fixture owns the one pool; flush explicitly for deterministic tests.
    monkeypatch.setattr(store, "start", lambda: None)
    monkeypatch.setattr(store, "close", lambda: None)

    def fixture_run(inv, manager):
        control = RunControl(inv, manager)
        for index in range(2):
            value = job(inv.id)["events"][0]
            value["event_id"] += str(index)
            value["provider_request_id"] += str(index)
            control.call(
                LifecycleState.exploring,
                lambda value=value: capture_response(
                    SimpleNamespace(json=lambda: {"usage_events": [value]})
                ),
                model=True,
            )
        manager.finalize(inv.id, LifecycleState.completed, lambda state: None)

    monkeypatch.setattr(kernel_loop, "run", fixture_run)
    client = test_client(create_app())
    run_ids = []
    for command in ("investigate", "verify", "report", "explain"):
        response = client.post(
            "/v1/investigations",
            json={
                "intent": command,
                "repository_path": str(tmp_path),
                "session_id": command + "-session",
            },
        )
        assert response.status_code == 201
        run_ids.append(response.json()["investigation_id"])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        store.flush()
        values = [database.run(store.profile_id, run) for run in run_ids]
        if all(
            value and value["finished_at"] and not value["pending_requests"] for value in values
        ):
            break
        time.sleep(0.02)
    else:
        pytest.fail("Fixture executions failed to persist their usage")
    usage = client.get("/v1/usage").json()
    assert usage["totals"]["total_tokens"] == 120
    assert usage["totals"]["llm_calls"] == 8
    assert len(usage["by_command"]) == 4
    for run_id in run_ids:
        assert client.get(f"/v1/investigations/{run_id}/usage").json()["total_tokens"] == 30
        stream = client.get(f"/v1/investigations/{run_id}/usage/stream")
        assert "event: complete" in stream.text
        persisted = json.loads(stream.text.split("data: ")[1].split("\n")[0])
        assert persisted["total_tokens"] == 30
