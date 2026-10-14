"""The real TUI footer, SSE delivery, and status interaction, without paid calls."""

import threading
from contextlib import contextmanager

import httpx
import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

from wizard.cli.display.usage import compact_tokens, counter
from wizard.cli.runtime_client import usage
from wizard.cli.tui.app import INTENT, WORKING, WizardTUI
from wizard.cli.tui.session import TuiSession


@contextmanager
def ui():
    class Output(DummyOutput):
        def get_size(self):
            return Size(rows=44, columns=120)

    with create_app_session(input=DummyInput(), output=Output()):
        yield WizardTUI()


@pytest.mark.parametrize(
    "tokens, expected",
    [
        (3460, "3.46k"),
        (3470, "3.47k"),
        (3480, "3.48k"),
        (55959, "55.96k"),
        (950, "950"),
        (0, "0"),
        (1000, "1.00k"),
        (1005, "1.01k"),
    ],
)
def test_compact_counts(tokens, expected):
    assert compact_tokens(tokens) == expected


def test_reconnect_keeps_confirmed_totals_and_clears_warning():
    session = TuiSession("investigate", "architecture")
    stream = usage.UsageStream.__new__(usage.UsageStream)
    stream.run_id = "current"
    stream.confirmed = None
    stream.on_update = session._consume
    stream.publish(snapshot())
    stream.publish({"transport_error": "Usage stream reconnecting"})
    assert session.usage["total_tokens"] == 3460
    assert "reconnecting" in counter(session.usage, compact=True)
    stream.publish(snapshot(revision=3, total_tokens=3470))
    assert "reconnecting" not in counter(session.usage, compact=True)
    assert session.usage["total_tokens"] == 3470


def test_reconnect_before_first_snapshot_is_pending_not_missing_metadata():
    assert counter({"transport_error": "reconnecting"}, 8, compact=True) == (
        "Tokens: pending | LLM calls: pending | Elapsed: 00:08 | reconnecting"
    )


def snapshot(run="current", revision=2, **changes):
    return {
        "run_id": run,
        "revision": revision,
        "total_tokens": 3460,
        "input_tokens": 2910,
        "output_tokens": 550,
        "llm_calls": 4,
        "incomplete": False,
        "pending_requests": 1,
        **changes,
    }


def test_exact_format_and_integer_state(monkeypatch):
    with ui() as app:
        app.state = WORKING
        app.session = TuiSession("investigate", "architecture", started_at=10)
        app.session._consume(
            {
                "event_type": "usage.updated",
                "investigation_id": "current",
                "payload": snapshot(),
            }
        )
        monkeypatch.setattr("wizard.cli.tui.app.time.monotonic", lambda: 18)
        assert (
            app._render_usage()[0][1]
            == "Tokens: 3.46k (in 2.91k / out 550) | LLM calls: 4 | Elapsed: 00:08"
        )
        app.scroll = 20
        assert "3.46k" in app._render_usage()[0][1]
        assert type(app.session.usage["total_tokens"]) is int
        assert app.usage_window.height == 1


def test_pending_is_not_unavailable_and_elapsed_is_live(monkeypatch):
    with ui() as app:
        app.session = TuiSession("verify", "runtime", started_at=10)
        monkeypatch.setattr("wizard.cli.tui.app.time.monotonic", lambda: 18)
        first = app._render_usage()[0][1]
        assert "pending" in first and "unavailable" not in first and "00:08" in first
        monkeypatch.setattr("wizard.cli.tui.app.time.monotonic", lambda: 19)
        assert "00:09" in app._render_usage()[0][1]


def test_stale_run_and_older_reconnect_snapshots_cannot_overwrite_current():
    session = TuiSession("investigate", "architecture", investigation_id="current")

    def consume(payload):
        session._consume(
            {
                "event_type": "usage.updated",
                "investigation_id": payload["run_id"],
                "payload": payload,
            }
        )

    consume(snapshot())
    consume(snapshot("previous", 99, total_tokens=99999))
    consume(snapshot(revision=1, total_tokens=1))
    consume(snapshot())
    assert session.usage["total_tokens"] == 3460
    final = snapshot(revision=3, total_tokens=5000, pending_requests=0)
    session._consume(
        {"event_type": "done", "investigation_id": "current", "usage": final}
    )
    consume(snapshot(revision=4, total_tokens=99999))
    assert session.usage["total_tokens"] == 5000


def test_new_run_resets_usage_before_subscription(monkeypatch):
    with ui() as app:
        app.session = TuiSession(
            "verify", "runtime", usage=snapshot(), investigation_id="previous"
        )
        app.family, app.target = "investigate", "architecture"
        monkeypatch.setattr(TuiSession, "start", lambda self: None)
        app._begin_work("architecture")
        assert app.session.usage is None
        assert app.session.investigation_id == ""
        assert "pending" in app._render_usage()[0][1]


def test_sse_reconnect_delivers_directly_once_without_progress_pacing(monkeypatch):
    import json

    client_class = httpx.Client
    requests = []
    callbacks = []
    session = TuiSession("investigate", "architecture", investigation_id="current")

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                503, json={"detail": "Run usage is awaiting PostgreSQL persistence"}
            )
        body = (
            "id: 2\nevent: usage\ndata: "
            + json.dumps(snapshot())
            + "\n\nevent: complete\ndata: {}\n\n"
        )
        return httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        usage.httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )

    def update(event):
        callbacks.append(event)
        session._consume(event)

    stream = usage.UsageStream(
        "http://127.0.0.1/current/usage/stream", "current", on_update=update
    )
    try:
        assert stream.completed.wait(3)
        assert len(requests) == 2
        assert stream.drain() == []
        assert session.usage["total_tokens"] == 3460
        assert "unavailable" not in counter(session.usage, compact=True)
        assert len(callbacks) == 2
    finally:
        stream.close()


def test_listener_is_scoped_to_each_worker():
    def callback(event):
        pass

    assert usage.usage_listener() is None
    with usage.listen_usage(callback):
        assert usage.usage_listener() is callback
        result = []
        worker = threading.Thread(target=lambda: result.append(usage.usage_listener()))
        worker.start()
        worker.join()
        assert result == [None]
    assert usage.usage_listener() is None


def test_status_uses_current_run_and_displays_requested_fields(monkeypatch):
    ready = threading.Event()
    report = {
        "profile_id": "local",
        "current_run": {
            "run_id": "current",
            "session_id": "session",
            "command": "investigate",
            "intent": "architecture",
            "status": "completed",
            "finished_at": "now",
            "total_tokens": 8420,
            "input_tokens": 6200,
            "output_tokens": 2220,
            "llm_calls": 12,
        },
        "totals": {
            "total_tokens": 52840,
            "input_tokens": 38200,
            "output_tokens": 14640,
            "llm_calls": 86,
        },
        "by_command": {
            name: {"total_tokens": value}
            for name, value in [
                ("investigate", 31200),
                ("verify", 14500),
                ("explain", 5640),
                ("report", 1500),
            ]
        },
    }

    def status(run_id=None):
        assert run_id == "current"
        return report

    monkeypatch.setattr(usage, "status", status)
    with ui() as app:
        app.state = INTENT
        app.session = TuiSession(
            "investigate", "architecture", investigation_id="current"
        )
        monkeypatch.setattr(app.app, "invalidate", ready.set)
        app.input.buffer.text = "/status"
        app._on_accept(app.input.buffer)
        assert ready.wait(2)
        assert "Command:        investigate" in app._usage_report
        assert "Intent:         architecture" in app._usage_report
        assert "Run tokens:     8,420" in app._usage_report
        assert "Total tokens:   52,840" in app._usage_report
        assert "Total LLM calls:86" not in app._usage_report
        assert "Total LLM calls: 86" in app._usage_report
        assert "investigate:    31,200" in app._usage_report


def test_status_error_preserves_backend_503_reason(monkeypatch):
    ready = threading.Event()

    def fail():
        raise RuntimeError(
            "Usage unavailable (HTTP 503): PostgreSQL usage persistence is not configured"
        )

    monkeypatch.setattr(usage, "status", fail)
    with ui() as app:
        app.state = INTENT
        monkeypatch.setattr(app.app, "invalidate", ready.set)
        app.input.buffer.text = "/status"
        app._on_accept(app.input.buffer)
        assert ready.wait(2)
        assert "HTTP 503" in app._usage_report
        assert "not configured" in app._usage_report
