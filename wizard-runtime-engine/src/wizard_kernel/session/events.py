"""Lightweight synchronous event bus for investigation lifecycle events.

Events decouple the loop from observers (logging, future webhooks, CLI output).
All emission is synchronous and in-process — no threads, no queues.

If a listener raises, the exception is caught and logged; it never crashes the loop.
"""
from __future__ import annotations

import logging
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


class EventBus:
    """Per-investigation event bus.  One bus per investigation — never shared."""

    def __init__(self, inv_id: str) -> None:
        self._inv_id = inv_id
        self._listeners: dict[str, list[Callable[[dict], None]]] = {}

    def on(self, event_type: str, listener: Callable[[dict], None]) -> None:
        """Register a listener for an event type."""
        self._listeners.setdefault(event_type, []).append(listener)

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Fire all listeners registered for `event_type`.
        Listener failures are logged but never propagated (invariant 4)."""
        data = {"investigation_id": self._inv_id, "event": event_type,
                **(payload or {})}
        for fn in self._listeners.get(event_type, []):
            try:
                fn(data)
            except Exception:  # noqa: BLE001
                log.warning("event listener for %r raised, ignoring", event_type, exc_info=True)


# Module-level factory — loop creates one per investigation
def create(inv_id: str) -> EventBus:
    return EventBus(inv_id)
