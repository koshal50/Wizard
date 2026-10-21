"""Runtime Engine client — sends requests and streams events.

The engine flow is: POST /v1/investigations to start, then poll
GET /v1/investigations/{id}/events for streamed progress, and finally
GET /v1/investigations/{id}/report once completed.

This module exposes:

    stream_events(request) -> Iterator[dict]
        A generator that yields typed event dicts as they arrive. Terminal
        events are "done" (carries final status + report + stats) and
        "engine_unavailable" (carries the connection error). Consumed by the
        TuiSession worker thread, which renders events live.

    RuntimeResponse
        Dataclass for structured response data (used by TuiSession).
"""

from __future__ import annotations

import json
import os
import time
import uuid
import urllib.error
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from wizard.cli.models.investigation_request import InvestigationRequest

_cancel_scope = ContextVar("cli_run_cancellation", default=None)


@contextmanager
def listen_cancel(stop_event, register_monitor, on_run=None):
    token = _cancel_scope.set((stop_event, register_monitor, on_run))
    try:
        yield
    finally:
        _cancel_scope.reset(token)

# Where the Runtime Engine lives. Overridable so a run can target an engine on
# another host or port without a code change — this is the only place the CLI
# hardcodes the engine's address, and the TUI and all four commands resolve
# through it.
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1/investigations"
POLL_INTERVAL = 1.0

# How many times the terminal branch re-reads the event log before giving up on
# it. See `_drain`'s caller: the tail of a finished run is worth fetching, but a
# loop that cannot end is worse than one that stops early.
_TAIL_DRAINS = 5


def base_url() -> str:
    """The Runtime Engine's investigations endpoint, from the environment.

    WIZARD_ENGINE_URL may name either the full endpoint
    ("http://host:8080/v1/investigations") or just the origin
    ("http://host:8080"), which is the shorter thing to type; a bare origin gets
    the API path appended. Read at call time rather than import time so a test
    or a wrapper can set it after this module is imported.
    """
    raw = (os.environ.get("WIZARD_ENGINE_URL") or "").strip()
    if not raw:
        return DEFAULT_BASE_URL
    raw = raw.rstrip("/")
    if raw.endswith("/v1/investigations"):
        return raw
    return f"{raw}/v1/investigations"


# Kept for callers that imported the old constant. Prefer base_url().
BASE_URL = DEFAULT_BASE_URL


@dataclass
class RuntimeResponse:
    """Response received from the Runtime Engine.

    Attributes:
        status: Response status — "accepted", "in_progress", "completed",
                "failed", or "engine_unavailable".
        message: Human-readable status message.
        data: Arbitrary response data from the Runtime Engine.
        timestamp: When the response was created.
    """

    status: str
    message: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _api_payload(request: InvestigationRequest) -> dict:
    """Map a CLI InvestigationRequest to the Runtime Engine API shape.

    `targets` is `intent.api_targets`, not `intent.targets`: a URL the user
    typed is a target too, just of the web plane, and the Runtime reads the
    browser ones out of this same array by their http prefix. Sending only the
    named file targets here is what previously made a typed URL vanish between
    the CLI and the planner.

    `question` is the user's sentence, sent as itself. Parsing it into targets
    is lossy by design — it keeps the words the command vocabulary recognises
    and drops the rest — so the sentence has to travel separately or the Planner
    is told what was aimed at and never what was asked.
    """
    return {
        "repository_path": request.repository.path,
        "intent": request.intent.action,
        "targets": request.intent.api_targets,
        "question": request.intent.question,
        "options": request.options.to_dict(),
    }


def _write_report(markdown: str, request: InvestigationRequest) -> "str | None":
    """Save the final report next to the run, returning the path written.

    The report command module already owns the naming policy (find the next free
    verification_report(N).md, never overwrite an earlier one) — this only calls
    it, so there is one place that decides what a report file is called.

    Returns None when there is nothing to write or the write failed. A failure
    here must not lose the report: the caller still has the markdown in hand and
    reports it in the stream.
    """
    if not markdown.strip():
        return None
    try:
        # Imported here rather than at module scope: commands/report.py imports
        # this module, so a top-level import would be circular.
        from wizard.cli.commands.report import next_report_path, save_report

        output_dir = Path(request.repository.path).resolve() / "output"
        path = next_report_path(output_dir, ".md")
        save_report(path, markdown)
        return str(path)
    except OSError as exc:
        # A read-only or vanished output directory. The run itself succeeded;
        # surface the path failure in the stream instead of aborting the report.
        return f"<could not save report: {exc}>"


def cancel_investigation(inv_id: str) -> bool:
    """Ask the Runtime Engine to stop an investigation.

    Returns True only if the engine ended up cancelled, False if it could not be
    reached, the id is unknown, or the investigation had already finished.

    A cancel is a request: the engine's run loop notices it between nodes, and
    terminal states are absorbing, so a cancel that arrives after the run's last
    node leaves it `completed`. The engine reports which of the two happened —
    that answer is what this returns, because "I asked" and "it stopped" are not
    the same claim.

    Closing the TUI without this leaves the investigation running: it keeps
    consuming budget and writing events that nobody is reading.
    """
    if not inv_id:
        return False
    try:
        # A bounded timeout: this runs on the worker thread while the user is
        # waiting for the UI to settle, so an unreachable engine must not hang
        # the cancel for the OS default (which can be minutes).
        req = urllib.request.Request(f"{base_url()}/{inv_id}", method="DELETE")
        with urllib.request.urlopen(req, timeout=2) as response:
            body = json.loads(response.read().decode())
        return bool(body.get("cancelled", body.get("status") == "cancelled"))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _engine_error(exc: Exception) -> str:
    """The best description of a failed Engine call, in the Engine's own words.

    A refusal from the Engine carries its reason in the JSON body's `detail` —
    "sandbox_mode='docker' was requested, but no Docker daemon is reachable:
    …". `str(exc)` reduces all of that to "HTTP Error 400: Bad Request", and
    since HTTPError subclasses URLError, the generic handler used to swallow it
    that way: the user saw a bare "engine_unavailable" and had no way to learn
    what the Engine objected to. Read the body; fall back to the status line.
    """
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
        except (ValueError, OSError):
            return f"HTTP {exc.code}: {exc.reason}"
        detail = body.get("detail") if isinstance(body, dict) else None
        if detail:
            return str(detail)
        return f"HTTP {exc.code}: {exc.reason}"
    return str(exc)


def stream_events(request: InvestigationRequest) -> Iterator[dict]:
    """Keep the monitor lifecycle tied to the existing command generator."""
    monitors = []
    try:
        yield from _stream_events(request, monitors)
    finally:
        for monitor in monitors:
            monitor.close()


def _stream_events(request: InvestigationRequest, monitors) -> Iterator[dict]:
    """Start an investigation and yield engine events as they arrive.

    Yields plain dicts. Progress events are forwarded verbatim from the
    engine (each has "seq", "event_type", "payload"). Two synthetic terminal
    events bookend the stream:

        {"event_type": "engine_unavailable", "error": "..."}
            The engine could not be reached / the stream broke. Terminal.

        {"event_type": "done", "status": "...", "report_markdown": "...",
         "report_path": "..." | None, "stats": {...}, "request": {...}}
            The investigation reached a terminal state. Always the last item
            on a successful run. `report_path` is the file the report was saved
            to, or None when there was no report or it could not be written.

    This is a generator: callers drive it with a for-loop and render each
    event however they like (push into a TUI session).
    """
    payload = _api_payload(request)
    api = base_url()
    control = _cancel_scope.get()
    def stopped():
        return bool(control and control[0].is_set())
    if stopped():
        return

    # 1. Start investigation
    from wizard.cli.runtime_client.account import account_headers
    auth_headers = account_headers()
    try:
        req = urllib.request.Request(
            api,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Idempotency-Key": uuid.uuid4().hex, **auth_headers},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            inv_id = data.get("investigation_id")
    except urllib.error.URLError as e:
        yield {"event_type": "engine_unavailable", "error": _engine_error(e)}
        return

    # 2. Poll events until the investigation reaches a terminal state
    if control and control[2]:
        control[2](inv_id)
    if stopped():
        # Cancellation may race the POST acknowledgement. Never abandon a run
        # once its ID becomes available, even if the UI has already settled.
        cancel_investigation(inv_id)
        return
    monitor = None
    yield {"event_type": "usage.pending", "investigation_id": inv_id, "payload": {}}
    if "usage_enabled" in data:
        from wizard.cli.runtime_client.usage import UsageStream, usage_listener
        monitor = UsageStream(f"{api}/{inv_id}/usage/stream", inv_id, on_update=usage_listener(), headers=auth_headers)
        monitors.append(monitor)
        if control:
            control[1](monitor)
    else:
        yield {"event_type": "usage.updated", "investigation_id": inv_id,
               "payload": {"incomplete": True, "persistence_error": "PostgreSQL usage persistence unavailable"}}
    seq = 0
    current_state = "unknown"
    status_data: dict = {}

    def _drain() -> Iterator[dict]:
        """Every event written since `seq`, as dicts, advancing `seq` past them.

        Its own function because it is needed twice: once per turn of the poll,
        and once more after the run is known to have stopped. See the terminal
        branch below for why the second call is not optional.
        """
        nonlocal seq
        changed_report = False
        url = f"{api}/{inv_id}/events?since_seq={seq}"
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=10) as response:
            for ev in json.loads(response.read().decode()):
                seq = max(seq, ev["seq"])
                if ev.get("event_type") == "report.updated":
                    changed_report = True
                else:
                    yield ev
        if changed_report:
            try:
                with urllib.request.urlopen(f"{api}/{inv_id}/report", timeout=5) as response:
                    report = json.loads(response.read().decode())
                yield {"event_type": "report.updated", "investigation_id": inv_id, "payload": report}
            except (urllib.error.URLError, ValueError):
                pass  # A report is optional while discovery is still running.

    while True:
        if stopped():
            return
        try:
            if monitor:
                yield from monitor.drain()
            yield from _drain()

            status_req = urllib.request.Request(f"{api}/{inv_id}", method="GET")
            with urllib.request.urlopen(status_req, timeout=10) as response:
                status_data = json.loads(response.read().decode())
                current_state = status_data.get("status", "unknown")
                # Ask the Runtime whether the run has stopped instead of keeping a
                # list of terminal states here. The list this replaced named only
                # completed/failed/cancelled, so when `incomplete` was added the
                # poll never ended and the caller waited on a finished run forever.
                if status_data.get("is_terminal") and status_data.get('report_ready', True):
                    # Drain the tail before leaving.
                    #
                    # Reading the events and asking whether the run has stopped
                    # are two separate requests, so anything the run emitted
                    # between them is not in hand when the second one answers.
                    # Breaking here discarded it — which is why a run that
                    # navigated to a page, took a snapshot and then typed into a
                    # form showed a trace that stopped at the page load, with
                    # every step after it invisible even though the engine had
                    # run and recorded all of them. The last thing a run does is
                    # the thing a reader most wants to see, and it was the one
                    # thing reliably thrown away.
                    #
                    # Bounded rather than `until empty`: a terminal run should
                    # have stopped emitting, and a loop that cannot end is worse
                    # than one that stops early. The bound only has to cover a
                    # straggler or two; anything still arriving after that is not
                    # part of this run's story.
                    for _ in range(_TAIL_DRAINS):
                        tail = list(_drain())
                        if not tail:
                            break
                        yield from tail
                    break
                # A reply with no `is_terminal` cannot be read as "still running":
                # the field is the only thing this loop has to go on, so its
                # absence means the Engine is not answering the question this
                # client asked. Spinning on it waits forever with nothing on
                # screen, which is the one outcome a caller cannot diagnose — so
                # say what happened and stop.
                if "is_terminal" not in status_data:
                    yield {
                        "event_type": "engine_unavailable",
                        "error": (f"the Engine at {api} reported status "
                                  f"{current_state!r} without saying whether the run "
                                  f"has stopped; it may be an older build"),
                    }
                    return
        except urllib.error.URLError as e:
            yield {"event_type": "engine_unavailable", "error": _engine_error(e)}
            return

        if monitor:
            until = time.monotonic() + POLL_INTERVAL
            while time.monotonic() < until:
                if stopped():
                    return
                yield from monitor.drain()
                time.sleep(min(0.1, max(0, until - time.monotonic())))
        else:
            if control:
                control[0].wait(POLL_INTERVAL)
            else:
                time.sleep(POLL_INTERVAL)

    # 3. Fetch the report if the run wrote one.
    # Asked for on any terminal state, not just "completed": a run that ended
    # `incomplete` has a report too — it is the same document, reporting goals
    # that stayed open — and gating on "completed" here meant the caller was told
    # there was no report for a run whose report was on disk. The endpoint answers
    # 409 when there is genuinely none, which is what the HTTPError handles.
    report_data: dict = {}
    if status_data.get("is_terminal"):
        try:
            report_req = urllib.request.Request(f"{api}/{inv_id}/report", method="GET")
            with urllib.request.urlopen(report_req, timeout=10) as response:
                report_data = json.loads(response.read().decode())
        except urllib.error.HTTPError:
            pass

    report_markdown = report_data.get("report_markdown", "")
    if report_data.get("runbook"):
        try:
            output = Path(request.repository.path).resolve() / "output"
            output.mkdir(parents=True, exist_ok=True)
            artifact = output / (inv_id + ".runbook.json")
            artifact.write_text(json.dumps(report_data["runbook"], indent=2, ensure_ascii=False), encoding="utf-8")
            with urllib.request.urlopen(f"{api}/{inv_id}/report/html", timeout=5) as response:
                artifact.with_suffix(".html").write_bytes(response.read())
        except (OSError, urllib.error.URLError):
            pass  # Keep the Markdown report even if a companion export fails.
    final_usage = monitor.final() if monitor else {"incomplete": True}
    yield {"event_type": "usage.updated", "investigation_id": inv_id, "payload": final_usage}
    yield {
        "event_type": "done",
        "status": current_state,
        "request": payload,
        "investigation_id": inv_id,
        "report_markdown": report_markdown or "No report available.",
        "runbook": report_data.get("runbook"),
        "report_path": _write_report(report_markdown, request),
        "stats": status_data,
        "usage": final_usage,
    }
