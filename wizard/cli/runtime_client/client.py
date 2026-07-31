"""Runtime Engine client — Step 4 of the CLI pipeline.

Sends InvestigationRequests to the Runtime Engine and receives responses.

The engine flow is: POST /v1/investigations to start, then poll
GET /v1/investigations/{id}/events for streamed progress, and finally
GET /v1/investigations/{id}/report once completed.

This module exposes that flow two ways over the SAME polling logic:

    stream_events(request) -> Iterator[dict]
        A generator that yields typed event dicts as they arrive. Terminal
        events are "done" (carries final status + report + stats) and
        "engine_unavailable" (carries the connection error). Consumed by the
        interactive TUI, which renders events live.

    send_request(request) -> RuntimeResponse
        The classic command path (wizard investigate / verify / report).
        A thin consumer of stream_events that prints each event exactly as
        before and returns the final RuntimeResponse. Behavior unchanged.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from rich.console import Console

from wizard.cli.models.investigation_request import InvestigationRequest

console = Console()

BASE_URL = "http://127.0.0.1:8080/v1/investigations"
POLL_INTERVAL = 1.0


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
    """Map a CLI InvestigationRequest to the Runtime Engine API shape."""
    return {
        "repository_path": request.repository.path,
        "intent": request.intent.action,
        "targets": request.intent.targets,
        "options": request.options.to_dict(),
    }


def stream_events(request: InvestigationRequest) -> Iterator[dict]:
    """Start an investigation and yield engine events as they arrive.

    Yields plain dicts. Progress events are forwarded verbatim from the
    engine (each has "seq", "event_type", "payload"). Two synthetic terminal
    events bookend the stream:

        {"event_type": "engine_unavailable", "error": "..."}
            The engine could not be reached / the stream broke. Terminal.

        {"event_type": "done", "status": "...", "report_markdown": "...",
         "stats": {...}, "request": {...}}
            The investigation reached a terminal state. Always the last item
            on a successful run.

    This is a generator: callers drive it with a for-loop and render each
    event however they like (print, or push into a TUI session).
    """
    payload = _api_payload(request)

    # 1. Start investigation
    try:
        req = urllib.request.Request(
            BASE_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            inv_id = data.get("investigation_id")
    except urllib.error.URLError as e:
        yield {"event_type": "engine_unavailable", "error": str(e)}
        return

    # 2. Poll events until the investigation reaches a terminal state
    seq = 0
    current_state = "unknown"
    status_data: dict = {}
    while True:
        try:
            events_url = f"{BASE_URL}/{inv_id}/events?since_seq={seq}"
            req = urllib.request.Request(events_url, method="GET")
            with urllib.request.urlopen(req) as response:
                events = json.loads(response.read().decode())
                for ev in events:
                    seq = max(seq, ev["seq"])
                    yield ev

            status_req = urllib.request.Request(f"{BASE_URL}/{inv_id}", method="GET")
            with urllib.request.urlopen(status_req) as response:
                status_data = json.loads(response.read().decode())
                current_state = status_data.get("status", "unknown")
                if current_state in ("completed", "failed", "cancelled"):
                    break
        except urllib.error.URLError as e:
            yield {"event_type": "engine_unavailable", "error": str(e)}
            return

        time.sleep(POLL_INTERVAL)

    # 3. Fetch the report if the run completed
    report_data: dict = {}
    if current_state == "completed":
        try:
            report_req = urllib.request.Request(f"{BASE_URL}/{inv_id}/report", method="GET")
            with urllib.request.urlopen(report_req) as response:
                report_data = json.loads(response.read().decode())
        except urllib.error.HTTPError:
            pass

    yield {
        "event_type": "done",
        "status": current_state,
        "request": payload,
        "report_markdown": report_data.get("report_markdown", "No report available."),
        "stats": status_data,
    }


def send_request(request: InvestigationRequest) -> RuntimeResponse:
    """Send an InvestigationRequest and print progress (classic command path).

    Consumes stream_events and prints each event exactly as the previous
    inline implementation did, then returns the final RuntimeResponse.
    """
    for ev in stream_events(request):
        ev_type = ev.get("event_type")

        if ev_type == "engine_unavailable":
            return RuntimeResponse(
                status="engine_unavailable",
                message=f"Could not connect to Runtime Engine at {BASE_URL}. Is it running?",
                data={"error": ev.get("error", "")},
            )

        if ev_type == "done":
            state = ev.get("status", "unknown")
            return RuntimeResponse(
                status=state,
                message=f"Investigation finished with status: {state}",
                data={
                    "request": ev.get("request", {}),
                    "report_markdown": ev.get("report_markdown", "No report available."),
                    "stats": ev.get("stats", {}),
                },
            )

        payload = ev.get("payload", {})
        if ev_type == "node.completed":
            console.print(f"[green]+[/green] Completed node [bold]{payload.get('node_id')}[/bold]")
        elif ev_type == "node.failed":
            console.print(
                f"[red]x[/red] Failed node [bold]{payload.get('node_id')}[/bold] "
                f"({payload.get('reason', 'execution_failed')})"
            )
        elif ev_type == "claim.admitted":
            console.print(
                f"  [cyan]->[/cyan] Found evidence: {payload.get('claim_type')} -> {payload.get('key')}"
            )
        elif ev_type == "goal.satisfied":
            console.print(f"[bold yellow]>> Goal Satisfied:[/bold yellow] {payload.get('goal_name')}")
        elif ev_type == "agent.consulted":
            console.print(f"[blue]*[/blue] Consulted Agent ({payload.get('agent_type')})")

    # stream_events always ends with a terminal event; this is unreachable.
    return RuntimeResponse(status="unknown", message="No terminal event received.")
