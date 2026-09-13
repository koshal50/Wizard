"""Event data structures for the live activity log.

BulletRow represents one dot in the Claude-Code-style activity log.
LiveState is the shared mutable state that the render loop reads and
the worker thread writes. All mutations go through a threading.Lock
in the owning TuiSession.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BulletRow:
    """One row in the activity log — maps to one dot.

    Lifecycle:
        ○  (hollow, pulsing)  while status == "running"
        ●  (green solid)      when status == "done"
        ●  (red solid)        when status == "error"

    The optional `detail` is rendered as a dim indented sub-line:
        ● Consulting Explorer
          └ Read 256 lines
    """

    step_name: str
    status: str = "running"       # "running" | "done" | "error"
    detail: str = ""              # dim sub-line text
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None

    def resolve(self, status: str, detail: str = "") -> None:
        """Mark this bullet as done or error."""
        self.status = status
        if detail:
            self.detail = detail
        self.ended_at = time.monotonic()
