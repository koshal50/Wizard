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
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from wizard.cli.models.investigation_request import InvestigationRequest

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
    event however they like (push into a TUI session).
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
