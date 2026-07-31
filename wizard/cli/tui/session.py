"""TuiSession — the shared state the TUI renders and the worker mutates.

One session per investigation launch. The main (prompt_toolkit) thread only
ever *reads* the snapshot fields; a single background worker thread consumes
`client.stream_events(request)` and *writes* them. All shared mutation goes
through `_lock`, and every write calls the injected `on_change` callback so the
app can `invalidate()` and redraw.

Nothing here talks to the engine directly — it reuses the existing
`stream_events` generator (reuse, don't rewrite). The token/cost meter is
explicitly MOCK: agents aren't wired yet, so we increment a local ledger per
event at a fixed synthetic rate. This is labelled as mock in the UI.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable

from wizard.cli.models.investigation_request import InvestigationRequest
from wizard.cli.runtime_client.client import stream_events

# Gerund words shown beside the flame, cycled by phase. Themed, wizardly.
GERUNDS = ["ideating", "divining", "unfurling", "conjuring", "scrying", "weaving"]

# Mock token economics — purely illustrative until agents report real usage.
# Each engine event is attributed a synthetic token cost; dollar cost is
# tokens * _RATE. TODO(engine): replace with real usage from agent responses.
_TOKENS_PER_EVENT = {
    "agent.consulted": 320,
    "node.completed": 140,
    "node.failed": 90,
    "claim.admitted": 60,
    "goal.satisfied": 40,
}
_DEFAULT_EVENT_TOKENS = 50
_RATE = 3.0e-6  # $ per token (mock)


@dataclass
class LogLine:
    """One narration line in the working view."""

    text: str
    style: str  # a wiz.* style name


@dataclass
class TuiSession:
    """Thread-safe state for a single investigation run."""

    request: InvestigationRequest
    on_change: Callable[[], None] = lambda: None

    # --- worker/runtime state (guarded by _lock) ---
    running: bool = False
    finished: bool = False
    status: str = "pending"          # pending|running|completed|failed|engine_unavailable
    report_markdown: str = ""
    activity: list[LogLine] = field(default_factory=list)
    steering: list[str] = field(default_factory=list)
    tokens: int = 0
    gerund_index: int = 0

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _thread: "threading.Thread | None" = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Derived read helpers (take the lock, return snapshots)
    # ------------------------------------------------------------------
    @property
    def cost(self) -> float:
        with self._lock:
            return self.tokens * _RATE

    @property
    def gerund(self) -> str:
        with self._lock:
            return GERUNDS[self.gerund_index % len(GERUNDS)]

    def snapshot_activity(self, last: int = 12) -> list[LogLine]:
        with self._lock:
            return list(self.activity[-last:])

    def snapshot(self) -> dict:
        """A consistent read of the scalar fields under one lock acquisition."""
        with self._lock:
            return {
                "running": self.running,
                "finished": self.finished,
                "status": self.status,
                "tokens": self.tokens,
                "cost": self.tokens * _RATE,
                "gerund": GERUNDS[self.gerund_index % len(GERUNDS)],
                "report_markdown": self.report_markdown,
            }

    # ------------------------------------------------------------------
    # Steering — local queue, wired to the engine later
    # ------------------------------------------------------------------
    def add_steering(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        with self._lock:
            self.steering.append(text)
            self.activity.append(LogLine(f'queued steering: "{text}"', "wiz.gerund"))
        # TODO(engine): when a mid-investigation steering endpoint exists,
        # flush self.steering to POST /v1/investigations/{id}/steer here.
        self.on_change()

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Spawn the background worker that streams engine events."""
        if self._thread is not None:
            return
        with self._lock:
            self.running = True
            self.status = "running"
            self.activity.append(LogLine("summoning the runtime…", "wiz.flow"))
        self.on_change()
        self._thread = threading.Thread(target=self._run, name="wiz-worker", daemon=True)
        self._thread.start()

    def _log(self, text: str, style: str) -> None:
        with self._lock:
            self.activity.append(LogLine(text, style))
        self.on_change()

    def _run(self) -> None:
        try:
            for ev in stream_events(self.request):
                self._consume(ev)
        except Exception as exc:  # never let the worker kill the UI
            with self._lock:
                self.status = "failed"
                self.finished = True
                self.running = False
                self.activity.append(LogLine(f"worker error: {exc}", "wiz.err"))
            self.on_change()

    def _consume(self, ev: dict) -> None:
        ev_type = ev.get("event_type", "")

        # Mock token accounting + gerund advance on every event.
        with self._lock:
            self.tokens += _TOKENS_PER_EVENT.get(ev_type, _DEFAULT_EVENT_TOKENS)
            self.gerund_index += 1

        if ev_type == "engine_unavailable":
            with self._lock:
                self.status = "engine_unavailable"
                self.finished = True
                self.running = False
                self.activity.append(
                    LogLine("the runtime did not answer — is it awake?", "wiz.err")
                )
            self.on_change()
            return

        if ev_type == "done":
            with self._lock:
                self.status = ev.get("status", "completed")
                self.report_markdown = ev.get("report_markdown", "")
                self.finished = True
                self.running = False
                self.activity.append(LogLine(f"investigation {self.status}", "wiz.ok"))
            self.on_change()
            return

        # Progress events -> human flow narration.
        payload = ev.get("payload", {})
        line, style = _narrate(ev_type, payload)
        if line:
            self._log(line, style)


def _narrate(ev_type: str, payload: dict) -> tuple[str, str]:
    """Map an engine event to a flow-narration line + style."""
    if ev_type == "agent.consulted":
        agent = (payload.get("agent_type") or "agent").lower()
        if "explorer" in agent:
            return "→ sent to the Explorer", "wiz.flow"
        if "verif" in agent:
            return "→ sent to the Verifier", "wiz.flow"
        return f"→ consulted {agent}", "wiz.flow"
    if ev_type == "node.completed":
        return f"✓ node {payload.get('node_id', '?')}  ← back to Planner", "wiz.ok"
    if ev_type == "node.failed":
        return (
            f"✗ node {payload.get('node_id', '?')} "
            f"({payload.get('reason', 'failed')})",
            "wiz.err",
        )
    if ev_type == "claim.admitted":
        return (
            f"found evidence · {payload.get('claim_type', '?')} → "
            f"{payload.get('key', '?')}",
            "wiz.evidence",
        )
    if ev_type == "goal.satisfied":
        return f"★ goal satisfied · {payload.get('goal_name', '?')}", "wiz.ok"
    return "", "wiz.flow"
