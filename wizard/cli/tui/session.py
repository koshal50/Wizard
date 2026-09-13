"""TuiSession — the shared state the TUI renders and the worker mutates.

One session per investigation launch. The main (prompt_toolkit) thread only
ever *reads* the snapshot fields; a single background worker thread consumes
the command service generators (investigate/verify/report/explain) and *writes*
them. All shared mutation goes through `_lock`, and every write calls the
injected `on_change` callback so the app can `invalidate()` and redraw.

The worker calls the appropriate command service function based on the selected
family, which internally calls `stream_events()`. The token/cost meter is
explicitly MOCK: agents aren't wired yet, so we increment a local ledger per
event at a fixed synthetic rate. This is labelled as mock in the UI.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from wizard.cli.models.investigation_request import RequestOptions
from wizard.cli.tui.events import BulletRow

# Gerund words shown beside the glyph, cycled by phase. Themed, wizardly.
GERUNDS = [
    "ideating", "divining", "unfurling", "conjuring", "scrying", "weaving",
    "channeling", "deciphering", "summoning", "transmuting", "invoking",
    "unraveling", "attuning", "distilling", "illuminating", "probing",
    "tracing", "sifting", "unearthing", "crystallizing",
]

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
class TuiSession:
    """Thread-safe state for a single investigation run."""

    family: str                   # "investigate" | "verify" | "report" | "explain"
    target: str | None            # e.g. "architecture", None for report
    on_change: Callable[[], None] = lambda: None

    # --- worker/runtime state (guarded by _lock) ---
    running: bool = False
    finished: bool = False
    cancelled: bool = False
    status: str = "pending"          # pending|running|completed|failed|engine_unavailable
    report_markdown: str = ""
    bullets: list[BulletRow] = field(default_factory=list)
    steering: list[str] = field(default_factory=list)
    tokens: int = 0
    gerund_index: int = 0
    elapsed_start: float = field(default_factory=time.monotonic)

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _thread: "threading.Thread | None" = field(default=None, repr=False)
    _running_bullet: "BulletRow | None" = field(default=None, repr=False)

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

    def snapshot_activity(self, last: int = 20) -> list[BulletRow]:
        with self._lock:
            return list(self.bullets[-last:])

    def snapshot(self) -> dict:
        """A consistent read of the scalar fields under one lock acquisition."""
        with self._lock:
            return {
                "running": self.running,
                "finished": self.finished,
                "cancelled": self.cancelled,
                "status": self.status,
                "tokens": self.tokens,
                "cost": self.tokens * _RATE,
                "gerund": GERUNDS[self.gerund_index % len(GERUNDS)],
                "report_markdown": self.report_markdown,
                "elapsed_start": self.elapsed_start,
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
            self.bullets.append(BulletRow(
                step_name=f'queued steering: "{text}"',
                status="done",
                detail="",
            ))
        # TODO(engine): when a mid-investigation steering endpoint exists,
        # flush self.steering to POST /v1/investigations/{id}/steer here.
        self.on_change()

    # ------------------------------------------------------------------
    # Bullet helpers
    # ------------------------------------------------------------------
    def _start_bullet(self, name: str) -> BulletRow:
        """Start a new running bullet and track it as the active one."""
        bullet = BulletRow(step_name=name, status="running")
        with self._lock:
            self.bullets.append(bullet)
            self._running_bullet = bullet
        self.on_change()
        return bullet

    def _resolve_running(self, status: str, detail: str = "") -> None:
        """Resolve the currently running bullet."""
        with self._lock:
            if self._running_bullet is not None:
                self._running_bullet.resolve(status, detail)
                self._running_bullet = None
        self.on_change()

    def _add_done_bullet(self, name: str, detail: str = "") -> None:
        """Add a bullet that's already resolved (done or error)."""
        bullet = BulletRow(step_name=name, status="done", detail=detail)
        bullet.ended_at = time.monotonic()
        with self._lock:
            self.bullets.append(bullet)
        self.on_change()

    def _add_error_bullet(self, name: str, detail: str = "") -> None:
        """Add a bullet that's already resolved as error."""
        bullet = BulletRow(step_name=name, status="error", detail=detail)
        bullet.ended_at = time.monotonic()
        with self._lock:
            self.bullets.append(bullet)
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
            self.elapsed_start = time.monotonic()
        self._start_bullet("summoning the runtime…")
        self._thread = threading.Thread(target=self._run, name="wiz-worker", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            # Import the appropriate command service function
            event_gen = self._get_event_generator()
            for ev in event_gen:
                if self.cancelled:
                    with self._lock:
                        self.status = "cancelled"
                        self.finished = True
                        self.running = False
                    self._resolve_running("error", "cancelled by user")
                    self._add_error_bullet("cancelled", "user pressed Esc")
                    self.on_change()
                    return
                self._consume(ev)
        except Exception as exc:  # never let the worker kill the UI
            with self._lock:
                self.status = "failed"
                self.finished = True
                self.running = False
            self._resolve_running("error", str(exc))
            self._add_error_bullet(f"worker error: {exc}")
            self.on_change()

    def _get_event_generator(self):
        """Import and call the appropriate command service function."""
        repo_path = os.getcwd()
        options = RequestOptions()

        if self.family == "investigate":
            from wizard.cli.commands.investigate import investigate
            return investigate(self.target, repo_path, options)
        elif self.family == "verify":
            from wizard.cli.commands.verify import verify
            return verify(self.target, repo_path, options)
        elif self.family == "report":
            from wizard.cli.commands.report import report
            return report(repo_path, options)
        elif self.family == "explain":
            from wizard.cli.commands.explain import explain
            return explain(self.target, repo_path, options)
        else:
            raise ValueError(f"Unknown command family: {self.family}")

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
            self._resolve_running("error", "the runtime did not answer")
            self._add_error_bullet(
                "the runtime did not answer — is it awake?",
                ev.get("error", "connection refused"),
            )
            self.on_change()
            return

        if ev_type == "done":
            with self._lock:
                self.status = ev.get("status", "completed")
                self.report_markdown = ev.get("report_markdown", "")
                self.finished = True
                self.running = False
            self._resolve_running("done", f"investigation {self.status}")
            self._add_done_bullet(
                f"investigation {self.status}",
                "",
            )
            self.on_change()
            return

        # Progress events -> Claude-Code-style bullet entries.
        payload = ev.get("payload", {})

        if ev_type == "agent.consulted":
            # Resolve the previous running bullet, start a new one
            agent = (payload.get("agent_type") or "agent").lower()
            if "explorer" in agent:
                label = "Consulting Explorer"
            elif "verif" in agent:
                label = "Consulting Verifier"
            else:
                label = f"Consulting {agent}"
            self._resolve_running("done")
            self._start_bullet(label)

        elif ev_type == "node.completed":
            node_id = payload.get("node_id", "?")
            self._resolve_running("done", f"node {node_id} completed")
            self._start_bullet(f"Processing node {node_id}")
            # Immediately resolve since the node is done
            self._resolve_running("done", "← back to Planner")

        elif ev_type == "node.failed":
            node_id = payload.get("node_id", "?")
            reason = payload.get("reason", "failed")
            self._resolve_running("error", f"node {node_id}: {reason}")

        elif ev_type == "claim.admitted":
            claim_type = payload.get("claim_type", "?")
            key = payload.get("key", "?")
            self._add_done_bullet(
                f"Found evidence · {claim_type}",
                f"→ {key}",
            )

        elif ev_type == "goal.satisfied":
            goal_name = payload.get("goal_name", "?")
            self._add_done_bullet(f"★ Goal satisfied · {goal_name}")
