"""Lightweight synchronous event bus for investigation lifecycle events.

Events decouple the loop from observers (logging, future webhooks, CLI output).
All emission is synchronous and in-process — no threads, no queues.

If a listener raises, the exception is caught and logged; it never crashes the loop.

CLI/WebSocket integration: call `bus.subscribe_all(fn)` to receive every event.
Call `bus.get_recent_events(since_seq)` to poll events since a given sequence number.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Any

log = logging.getLogger(__name__)

# Typed event names — add here as new phases are implemented
InvestigationStarted = "investigation.started"
StateTransitioned    = "investigation.state_changed"
NodeCompleted        = "node.completed"
NodeFailed           = "node.failed"
ClaimAdmitted        = "claim.admitted"
GoalSatisfied        = "goal.satisfied"
BudgetLow            = "budget.low"
BudgetExhausted      = "budget.exhausted"
ReportGenerated      = "report.generated"
AgentConsulted       = "agent.consulted"
ToolRejected         = "tool.rejected"
AgentDecided         = "agent.decided"        # B8: the decision itself (not browser-specific)
BrowserNavigated     = "browser.navigated"    # narration plane — discrete browser events
BrowserActed         = "browser.acted"
BrowserExtracted     = "browser.extracted"


@dataclass
class InvestigationEvent:
    """A single investigation lifecycle event — immutable after creation."""
    seq: int
    investigation_id: str
    event_type: str
    payload: dict
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Per-investigation event bus.  One bus per investigation — never shared.

    Supports two integration patterns:
    1. Push: register a listener with bus.on(event_type, fn) or bus.subscribe_all(fn)
    2. Poll: call bus.get_recent_events(since_seq=N) to retrieve new events since N
    """

    def __init__(self, inv_id: str) -> None:
        self._inv_id = inv_id
        self._listeners: dict[str, list[Callable[[dict], None]]] = {}
        self._all_listeners: list[Callable[[InvestigationEvent], None]] = []
        self._history: list[InvestigationEvent] = []
        self._seq = 0

    def on(self, event_type: str, listener: Callable[[dict], None]) -> None:
        """Register a listener for a specific event type."""
        self._listeners.setdefault(event_type, []).append(listener)

    def subscribe_all(self, listener: Callable[[InvestigationEvent], None]) -> None:
        """Register a listener that receives every event as an InvestigationEvent.

        Use this for CLI progress streaming or WebSocket integration.
        The listener receives a structured InvestigationEvent with a monotonic seq number.
        """
        self._all_listeners.append(listener)

    def get_recent_events(self, since_seq: int = 0) -> list[InvestigationEvent]:
        """Return all events with seq > since_seq. Thread-safe (list reads are atomic in CPython).

        Use this for poll-based CLI output: track the last seq number received
        and call this on each poll to get only new events.
        """
        return [e for e in self._history if e.seq > since_seq]

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Fire all listeners registered for `event_type`.
        Listener failures are logged but never propagated (invariant 4).
        All events are appended to the immutable history for polling."""
        self._seq += 1
        data = {"investigation_id": self._inv_id, "event": event_type,
                **(payload or {})}

        # Append to immutable history (polling interface)
        event = InvestigationEvent(
            seq=self._seq,
            investigation_id=self._inv_id,
            event_type=event_type,
            payload=data,
        )
        self._history.append(event)

        # Fire typed listeners
        for fn in self._listeners.get(event_type, []):
            try:
                fn(data)
            except Exception:  # noqa: BLE001
                log.warning("event listener for %r raised, ignoring", event_type, exc_info=True)

        # Fire universal listeners (CLI/WebSocket)
        for fn in self._all_listeners:
            try:
                fn(event)
            except Exception:  # noqa: BLE001
                log.warning("universal event listener raised, ignoring", exc_info=True)


_BUSSES: dict[str, EventBus] = {}

def get_recent_events(since_seq: int, inv_id: str) -> list[InvestigationEvent]:
    """Retrieve recent events from the in-memory bus for an investigation."""
    bus = _BUSSES.get(inv_id)
    if not bus:
        return []
    return bus.get_recent_events(since_seq)

# Module-level factory — loop creates one per investigation
def create(inv_id: str) -> EventBus:
    bus = EventBus(inv_id)
    _BUSSES[inv_id] = bus
    return bus
