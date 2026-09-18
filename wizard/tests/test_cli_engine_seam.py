"""The CLI's side of the engine seam.

The CLI reaches the planner and the two agents through three option keys that
the Runtime reads out of the request's `options` dict. Nothing in the CLI's
source says so — the coupling is by key name across a process boundary — so the
tests here assert it against the Runtime's own factories rather than against
strings this repo happens to contain.

The other half is what the CLI does with a run once it has one: save the report,
and stop the investigation in the engine when the user cancels. Both are checked
against a stub engine that records what it was asked to do.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from wizard.cli.models.investigation_request import (
    InvestigationRequest,
    RepositoryInfo,
    RequestOptions,
)
from wizard.cli.models.intent import Intent
from wizard.cli.runtime_client import client as runtime_client


# ── A stub Runtime Engine ─────────────────────────────────────────────────────

class _StubEngine:
    """A minimal stand-in for the kernel's HTTP surface.

    Records every request it receives so a test can assert on the wire shape,
    and serves canned replies so the client's poll loop terminates immediately.
    """

    def __init__(self, *, status: str = "completed", report: str = "# Report\n\nbody\n"):
        self.requests: list[tuple[str, str, dict | None]] = []  # (method, path, body)
        self.status = status
        self.report = report
        self.investigation_id = "inv_stub001"
        # What the engine holds after a DELETE. The real route reports the state it
        # actually ends in, which is not always "cancelled".
        self.cancel_status = "cancelled"
        # Set False to stand in for an Engine that does not answer "has this run
        # stopped" — an older build, or anything else that speaks a partial
        # version of the contract.
        self.reports_is_terminal = True
        # Events the engine writes AFTER answering the first events request —
        # i.e. in the window between the client's events fetch and its status
        # fetch. Empty unless a test is exercising that window; see
        # `test_the_end_of_a_run_reaches_the_caller`.
        self.tail_events: list[dict] = []
        self._event_fetches = 0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence the test output
                pass

            def _record(self, body=None):
                stub.requests.append((self.command, self.path, body))

            def _send(self, code, payload):
                raw = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode() if length else ""
                self._record(json.loads(raw) if raw else None)
                self._send(201, {"investigation_id": stub.investigation_id,
                                 "status": "created"})

            def do_GET(self):
                self._record()
                if self.path.endswith("/report"):
                    # The endpoint's real contract: the report is served whenever
                    # the run wrote one, and 409s when there is genuinely none. A
                    # failed or cancelled run writes nothing (loop.run returns
                    # before reporting), so serving a document here would have the
                    # double assert something the Engine never does — and the
                    # client's 409 path is the half of it worth exercising.
                    if stub.status in ("failed", "cancelled"):
                        self._send(409, {"detail": f"No report for {stub.investigation_id!r} yet"})
                    else:
                        self._send(200, {"investigation_id": stub.investigation_id,
                                         "report_markdown": stub.report,
                                         "report_path": "engine-side.md"})
                elif "/events" in self.path:
                    since = int(self.path.split("since_seq=")[-1]) if "since_seq=" in self.path else 0
                    stub._event_fetches += 1
                    events = [{"seq": 1, "event_type": "investigation.started",
                               "investigation_id": stub.investigation_id,
                               "payload": {"investigation_id": stub.investigation_id}}]
                    # The tail is only on the wire from the second fetch on, so a
                    # client that stops at the first one cannot have seen it.
                    if stub._event_fetches > 1:
                        events += stub.tail_events
                    self._send(200, [e for e in events if e["seq"] > since])
                else:
                    # `is_terminal` is part of the status contract, not decoration:
                    # it is how the client knows the poll has ended. A double that
                    # omits it is standing in for an Engine that does not exist,
                    # and the client's reply to that is to report the Engine as
                    # unusable rather than wait on it.
                    payload = {"investigation_id": stub.investigation_id,
                               "status": stub.status, "nodes_completed": 2}
                    if stub.reports_is_terminal:
                        payload["is_terminal"] = stub.status in (
                            "completed", "incomplete", "failed", "cancelled")
                    self._send(200, payload)

            def do_DELETE(self):
                self._record()
                self._send(200, {"investigation_id": stub.investigation_id,
                                 "status": stub.cancel_status,
                                 "cancelled": stub.cancel_status == "cancelled"})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def origin(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def engine(monkeypatch):
    stub = _StubEngine()
    monkeypatch.setenv("WIZARD_ENGINE_URL", stub.origin)
    yield stub
    stub.stop()


def _request(options: RequestOptions) -> InvestigationRequest:
    return InvestigationRequest(
        repository=RepositoryInfo(path="/repo"),
        intent=Intent(action="investigate", targets=["architecture"]),
        options=options,
    )


# ── The option keys the Runtime reads ─────────────────────────────────────────

def test_options_default_to_no_seam_urls():
    """An unconfigured CLI run must not invent an endpoint."""
    data = RequestOptions().to_dict()
    assert "planner_url" not in data
    assert "agent_explorer_url" not in data
    assert "agent_verifier_url" not in data


def test_options_serialize_the_seam_urls():
    options = RequestOptions(
        planner_url="http://p:8787",
        agent_explorer_url="http://a:8100/agent/explorer",
        agent_verifier_url="http://a:8100/agent/verifier",
    )
    data = options.to_dict()
    assert data["planner_url"] == "http://p:8787"
    assert data["agent_explorer_url"] == "http://a:8100/agent/explorer"
    assert data["agent_verifier_url"] == "http://a:8100/agent/verifier"


def test_serialized_options_actually_reach_the_runtimes_factories():
    """The contract test: the CLI's dict drives the Runtime's port selection.

    These are the Runtime's own factories, not a re-implementation — if the CLI
    ever renamed a key, this fails here instead of silently degrading every run
    to the Runtime's offline fallbacks.
    """
    from wizard_kernel.ports.agents import MockExplorer, MockVerifier, get_agents
    from wizard_kernel.ports.planner import HttpPlanner, MockPlanner, get_planner

    offline = RequestOptions().to_dict()
    assert isinstance(get_planner(offline.get("planner_url")), MockPlanner)
    assert isinstance(get_agents(offline)[0], MockExplorer)
    assert isinstance(get_agents(offline)[1], MockVerifier)

    wired = RequestOptions(
        planner_url="http://127.0.0.1:8787",
        agent_explorer_url="http://127.0.0.1:8100/agent/explorer",
        agent_verifier_url="http://127.0.0.1:8100/agent/verifier",
    ).to_dict()
    assert isinstance(get_planner(wired.get("planner_url")), HttpPlanner)
    explorer, verifier = get_agents(wired)
    assert not isinstance(explorer, MockExplorer)
    assert not isinstance(verifier, MockVerifier)


def test_the_request_payload_puts_options_under_the_options_key():
    payload = runtime_client._api_payload(_request(
        RequestOptions(planner_url="http://p:8787")))
    assert payload["repository_path"] == "/repo"
    assert payload["intent"] == "investigate"
    assert payload["targets"] == ["architecture"]
    assert payload["options"]["planner_url"] == "http://p:8787"


# ── from_env ──────────────────────────────────────────────────────────────────

def test_from_env_reads_every_supported_variable():
    options = RequestOptions.from_env({
        "WIZARD_PLANNER_URL": "http://p:8787",
        "WIZARD_EXPLORER_URL": "http://a:8100/agent/explorer",
        "WIZARD_VERIFIER_URL": "http://a:8100/agent/verifier",
        "WIZARD_SANDBOX_MODE": "docker",
        "WIZARD_BUDGET": "42",
        "WIZARD_MAX_CONTEXT_TOKENS": "2048",
        "WIZARD_BROWSER": "yes",
        "WIZARD_ALLOWED_DOMAINS": "localhost, example.com",
    })
    assert options.planner_url == "http://p:8787"
    assert options.agent_explorer_url == "http://a:8100/agent/explorer"
    assert options.agent_verifier_url == "http://a:8100/agent/verifier"
    assert options.sandbox_mode == "docker"
    assert options.budget == 42
    assert options.max_context_tokens == 2048
    assert options.browser_enabled is True
    assert options.allowed_domains == ("localhost", "example.com")


def test_from_env_with_nothing_set_leaves_the_defaults_alone():
    assert RequestOptions.from_env({}) == RequestOptions()


@pytest.mark.parametrize("blank", ["", "   "])
def test_from_env_treats_a_blank_variable_as_unset(blank):
    """An empty value is a variable someone exported and never filled in."""
    options = RequestOptions.from_env({"WIZARD_PLANNER_URL": blank})
    assert options.planner_url is None
    assert "planner_url" not in options.to_dict()


def test_from_env_refuses_a_malformed_number():
    """Silently ignoring a typo'd budget would run under a limit nobody chose."""
    with pytest.raises(ValueError, match="WIZARD_BUDGET"):
        RequestOptions.from_env({"WIZARD_BUDGET": "lots"})


# ── Engine address ────────────────────────────────────────────────────────────

def test_base_url_defaults_to_the_local_engine(monkeypatch):
    monkeypatch.delenv("WIZARD_ENGINE_URL", raising=False)
    assert runtime_client.base_url() == "http://127.0.0.1:8080/v1/investigations"


@pytest.mark.parametrize("value", [
    "http://host:9000",
    "http://host:9000/",
    "http://host:9000/v1/investigations",
    "http://host:9000/v1/investigations/",
])
def test_base_url_accepts_a_bare_origin_or_the_full_endpoint(monkeypatch, value):
    monkeypatch.setenv("WIZARD_ENGINE_URL", value)
    assert runtime_client.base_url() == "http://host:9000/v1/investigations"


def test_base_url_is_read_per_call_not_at_import(monkeypatch):
    monkeypatch.setenv("WIZARD_ENGINE_URL", "http://one:1")
    assert runtime_client.base_url().startswith("http://one:1")
    monkeypatch.setenv("WIZARD_ENGINE_URL", "http://two:2")
    assert runtime_client.base_url().startswith("http://two:2")


# ── Cancellation ──────────────────────────────────────────────────────────────

def test_cancel_asks_the_engine_to_stop_the_investigation(engine):
    assert runtime_client.cancel_investigation("inv_stub001") is True
    assert engine.requests == [("DELETE", "/v1/investigations/inv_stub001", None)]


def test_cancel_without_an_id_never_calls_the_engine(engine):
    """Cancelled before the Runtime accepted it — there is nothing to cancel."""
    assert runtime_client.cancel_investigation("") is False
    assert engine.requests == []


def test_cancel_does_not_claim_success_when_the_run_had_already_finished(engine):
    """A cancel is a request, and the engine is entitled to say it was too late.

    Terminal states are absorbing, so an investigation that completed a moment
    before the DELETE keeps `completed`. Reporting that as a successful cancel
    would tell the user their run stopped when it actually ran to completion.
    """
    engine.cancel_status = "completed"
    assert runtime_client.cancel_investigation("inv_stub001") is False


def test_cancel_reports_failure_when_the_engine_is_gone(monkeypatch):
    monkeypatch.setenv("WIZARD_ENGINE_URL", "http://127.0.0.1:1")
    assert runtime_client.cancel_investigation("inv_any") is False


def test_cancel_reports_failure_on_an_unreadable_reply(engine, monkeypatch):
    """A 200 whose body is not the engine's shape is not a confirmed cancel."""
    engine.cancel_status = None  # serializes as null, not "cancelled"
    assert runtime_client.cancel_investigation("inv_stub001") is False


# ── Report on disk ────────────────────────────────────────────────────────────

def test_a_completed_run_writes_its_report(engine, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    done = [e for e in runtime_client.stream_events(
        _request(RequestOptions(planner_url="http://p:8787")))][-1]

    assert done["event_type"] == "done"
    assert done["status"] == "completed"
    assert done["investigation_id"] == "inv_stub001"
    assert done["report_path"]

    written = tmp_path / "output"
    files = sorted(p.name for p in written.iterdir())
    assert files == ["verification_report(1).md"]
    assert (written / files[0]).read_text(encoding="utf-8") == "# Report\n\nbody\n"


def test_a_status_without_is_terminal_stops_the_poll_instead_of_spinning(engine,
                                                                        monkeypatch,
                                                                        tmp_path):
    """The poll has one thing to go on, and its absence is not "keep waiting".

    A reply that names a state but not whether the run has stopped cannot be read
    either way. Treating it as "still running" was an infinite poll: no output, no
    error, nothing to act on — the caller waits forever on a run that has already
    finished. Reporting the Engine as unusable is the diagnosable outcome.
    """
    engine.reports_is_terminal = False
    monkeypatch.chdir(tmp_path)

    events = list(runtime_client.stream_events(_request(RequestOptions())))

    assert events[-1]["event_type"] == "engine_unavailable"
    assert "is_terminal" in events[-1]["error"] or "stopped" in events[-1]["error"]
    assert not (tmp_path / "output").exists()


def test_the_engine_was_sent_the_cli_options(engine, monkeypatch, tmp_path):
    """The whole point of the phase: what the CLI serializes is what runs."""
    monkeypatch.chdir(tmp_path)
    list(runtime_client.stream_events(_request(RequestOptions(
        planner_url="http://127.0.0.1:8787",
        agent_explorer_url="http://127.0.0.1:8100/agent/explorer",
        agent_verifier_url="http://127.0.0.1:8100/agent/verifier",
    ))))

    method, path, body = engine.requests[0]
    assert (method, path) == ("POST", "/v1/investigations")
    assert body["options"]["planner_url"] == "http://127.0.0.1:8787"
    assert body["options"]["agent_explorer_url"] == "http://127.0.0.1:8100/agent/explorer"
    assert body["options"]["agent_verifier_url"] == "http://127.0.0.1:8100/agent/verifier"


def test_a_failed_run_saves_no_report(engine, monkeypatch, tmp_path):
    engine.status = "failed"
    monkeypatch.chdir(tmp_path)
    done = [e for e in runtime_client.stream_events(_request(RequestOptions()))][-1]
    assert done["status"] == "failed"
    assert done["report_path"] is None
    assert not (tmp_path / "output").exists()


def test_reports_are_numbered_and_never_overwritten(monkeypatch, tmp_path):
    from wizard.cli.commands.report import next_report_path, save_report

    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    first = next_report_path(output_dir, ".md")
    save_report(first, "first")
    second = next_report_path(output_dir, ".md")
    save_report(second, "second")

    assert first.name == "verification_report(1).md"
    assert second.name == "verification_report(2).md"
    assert first.read_text(encoding="utf-8") == "first"


# ── The TUI's cancel path ─────────────────────────────────────────────────────

def test_escape_cancels_the_investigation_in_the_engine(engine):
    """Esc has to stop the run, not just the view of it.

    The session knows the engine's id from the events it consumed; without
    using it here the engine keeps burning budget in its own process.
    """
    from wizard.cli.tui.session import TuiSession

    session = TuiSession(family="investigate", target="architecture")
    session._consume({"seq": 1, "event_type": "investigation.started",
                      "investigation_id": "inv_stub001", "payload": {}})
    assert session.investigation_id == "inv_stub001"

    session.cancel()

    assert session.status == "cancelled"
    assert session.finished and not session.running
    assert ("DELETE", "/v1/investigations/inv_stub001", None) in engine.requests

    bullets = session.snapshot_activity()
    assert any("inv_stub001" in b.text for b in bullets), \
        [b.text for b in bullets]


def test_the_session_picks_up_seam_urls_from_the_environment(monkeypatch):
    """The TUI must build its options from the environment, or it can only ever
    reach the Runtime's offline fallbacks."""
    from wizard.cli.tui.session import TuiSession

    monkeypatch.setenv("WIZARD_PLANNER_URL", "http://127.0.0.1:8787")
    session = TuiSession(family="report", target=None)
    captured = {}

    def fake_report(repo_path=None, options=None, intent_text=""):
        captured["options"] = options
        return iter(())

    monkeypatch.setattr("wizard.cli.commands.report.report", fake_report)
    list(session._get_event_generator())

    assert captured["options"] is not None
    assert captured["options"].planner_url == "http://127.0.0.1:8787"


# ── The user's sentence ───────────────────────────────────────────────────────
#
# `targets` holds only the words the command vocabulary recognises. A sentence
# that names something else — "why does the login form lose my session" — has no
# target in it at all, so before `question` the Runtime was told what was aimed
# at and never what was asked, and every phrasing of one command planned
# identically. These tests are about the sentence surviving the trip.


def test_the_payload_carries_the_users_sentence_verbatim():
    request = InvestigationRequest(
        repository=RepositoryInfo(path="/repo"),
        intent=Intent(
            action="investigate",
            targets=["architecture"],
            question="why does the login form lose my session",
        ),
        options=RequestOptions(),
    )
    payload = runtime_client._api_payload(request)
    assert payload["question"] == "why does the login form lose my session"
    # And the family still travels as itself: the two are different inputs, and
    # the Runtime types `intent` as one of four verbs.
    assert payload["intent"] == "investigate"


def test_a_menu_driven_request_sends_an_empty_sentence_not_a_missing_key():
    """The Runtime reads `question` as a plain string, so it must always be one.

    Omitting the key would make every menu-driven run depend on a default
    somewhere else; sending the command family here instead would tell the
    Planner the user typed the word "report".
    """
    payload = runtime_client._api_payload(_request(RequestOptions()))
    assert payload["question"] == ""


@pytest.mark.parametrize("action", ["investigate", "verify", "report", "explain"])
def test_every_command_family_carries_the_sentence(action):
    """All four, because the sentence is a property of the request, not of one
    command — and the family is the only other thing the Planner can read."""
    from wizard.cli.parser.intent_builder import build_intent

    intent = build_intent(
        action=action,
        target="architecture" if action in ("investigate", "explain") else None,
        targets=["architecture"] if action in ("investigate", "explain") else None,
        question="why does the login form lose my session",
    )
    request = InvestigationRequest(
        repository=RepositoryInfo(path="/repo"), intent=intent,
        options=RequestOptions(),
    )
    assert runtime_client._api_payload(request)["question"] == "why does the login form lose my session"


# ---------------------------------------------------------------------------
# An adopted Runtime must be one this CLI can actually talk to
# ---------------------------------------------------------------------------

def _kernel_spec():
    from wizard.cli.tui import services
    return [s for s in services.build_specs() if s.key == "kernel"][0]


def test_a_runtime_that_does_not_accept_the_question_is_refused(monkeypatch, tmp_path):
    """An older Runtime on the port must not be adopted silently.

    Pydantic ignores fields it does not know, so a Runtime built before
    `question` existed accepts the request and drops the user's sentence: the
    planner is handed a request with nothing to plan from and the run proceeds
    anyway. A degraded run that looks like a working one is the outcome this
    whole project is arranged against, so the port is asked before it is used.
    """
    from wizard.cli.tui import services

    monkeypatch.setattr(services, "healthy", lambda spec, timeout=1.5: True)
    monkeypatch.setattr(services, "missing_request_fields",
                        lambda port, timeout=3.0: ("question",))
    state = services.ensure_service(_kernel_spec(), tmp_path)
    assert state.status == "unavailable"
    assert state.ok is False
    assert "question" in state.detail
    assert str(state.spec.port) in state.detail


def test_a_runtime_that_accepts_the_question_is_adopted(monkeypatch, tmp_path):
    """The probe must not take a working Runtime away from the user."""
    from wizard.cli.tui import services

    monkeypatch.setattr(services, "healthy", lambda spec, timeout=1.5: True)
    monkeypatch.setattr(services, "missing_request_fields",
                        lambda port, timeout=3.0: ())
    state = services.ensure_service(_kernel_spec(), tmp_path)
    assert state.status == "adopted"
    assert state.ok is True


def test_a_schema_that_cannot_be_read_is_not_a_missing_field(monkeypatch):
    """Unreadable is not the same as absent.

    An unreachable Runtime is the health probe's to report. Reporting it here
    as well would name the wrong fault — and would refuse a Runtime that is
    merely slow to publish its schema.
    """
    import urllib.error
    from wizard.cli.tui import services

    def _boom(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(services.urllib.request, "urlopen", _boom)
    assert services.missing_request_fields(8080) == ()


def test_the_end_of_a_run_reaches_the_caller(engine):
    """A finished run's last events are not optional.

    Reading the event log and asking whether the run has stopped are two
    separate requests, so the engine can write an event between them — and it
    routinely does, because the last thing a run does (the click that submits a
    form, the report it writes) happens right before it goes terminal.

    This was not hypothetical. The client broke out of its poll on the terminal
    reply without re-reading the log, so a run that navigated to a page, took a
    snapshot and then typed into two fields and pressed submit showed a trace
    that stopped at the page load. Every step after it was invisible on screen
    while the engine had run and recorded all of them — the reader saw a wizard
    that opened a browser and did nothing to the page it opened.
    """
    engine.tail_events = [
        {"seq": 2, "event_type": "browser.acted", "investigation_id": engine.investigation_id,
         "payload": {"tool": "browser_type", "selector": 'role=textbox[name="Email"]'}},
        {"seq": 3, "event_type": "done", "investigation_id": engine.investigation_id,
         "payload": {}},
    ]
    request = _request(RequestOptions(browser_enabled=True))
    # The terminal `done` event the client synthesises carries no seq, so the
    # identity of an event is its type here, not its number.
    seen = [ev.get("event_type") for ev in runtime_client.stream_events(request)]

    assert "browser.acted" in seen, (
        "the event the engine wrote after the status reply never reached the caller; "
        f"it saw {seen}"
    )


def test_a_terminal_reply_does_not_start_an_endless_drain(engine):
    """The tail drain is bounded. A run that keeps emitting after it is terminal
    is a bug elsewhere, and a client that waits on it forever is a worse one —
    the caller gets no report and no error, just a spinner."""
    engine.tail_events = []
    request = _request(RequestOptions())
    seen = list(runtime_client.stream_events(request))

    assert seen[-1]["event_type"] == "done"
    assert engine._event_fetches <= 10, (
        f"the client read the event log {engine._event_fetches} times for one finished run"
    )
