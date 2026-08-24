"""Stage 7b — Context Audit (architecture §12, §22).

Records every context supply onto the investigation's event log so the exact
projection each agent received is reconstructable. Reuses the existing EventBus
(session.events) rather than standing up a second log — the architecture's
"append context_supplied to the event log" maps directly onto bus.emit(...),
and the bus already owns seq numbering, history, and invariant-4 exception
swallowing.

The payload is deliberately compact — section ids + token totals + flags, never
the full rendered content, which would bloat the event history for no gain.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from wizard_kernel.context.sections import ContextSection

if TYPE_CHECKING:
    from wizard_kernel.session.events import EventBus

# New event type; defined here so events.py needs no edit (bus.emit takes any str).
CONTEXT_SUPPLIED = "context_supplied"


class ContextAudit:
    def __init__(self, bus: "EventBus") -> None:
        self._bus = bus

    def record(
        self,
        agent_type: str,
        node_id: str,
        sections: list[ContextSection],
        *,
        from_cache: bool = False,
        rejected: bool = False,
        reason: str | None = None,
    ) -> None:
        self._bus.emit(CONTEXT_SUPPLIED, {
            "agent_type": agent_type,
            "node_id": node_id,
            "section_ids": [s.id for s in sections],
            "token_total": sum(s.token_cost for s in sections),
            "from_cache": from_cache,
            "rejected": rejected,
            "reason": reason,
        })
