from dataclasses import dataclass, field
from datetime import datetime, timezone
from wizard_kernel.contracts.status import LifecycleState


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Investigation:
    id: str
    repository_path: str
    intent: str
    targets: list[str]
    options: dict
    # What the user typed, verbatim, when they typed anything. Held beside
    # `intent` (the command family) rather than folded into it because the two
    # are different inputs, and because this one is never validated — it is the
    # Planner's to read, not the kernel's to interpret. Defaulted so an
    # investigation persisted before this field existed still restores.
    question: str = ""
    state: LifecycleState = LifecycleState.created
    budget_total: int = 40
    budget_remaining: int = 40
    nodes_completed: int = 0
    claims_count: int = 0
    last_event: str = ""
    active_goals: list[dict] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
