"""Priority engine — picks next ready node deterministically. No LLM. Phase 3."""
from wizard_kernel.contracts.node import InvestigationNode


def next_ready(
    nodes: list[InvestigationNode],
    completed_ids: set[str],
    goal_urgency: dict[str, float] | None = None,
) -> InvestigationNode | None:
    """Return highest-priority node whose dependencies are all complete."""
    urgency = goal_urgency or {}
    ready = [
        n for n in nodes
        if n.state == "waiting" and set(n.depends_on).issubset(completed_ids)
    ]
    if not ready:
        return None
    # score = goal_urgency + (1 if no depends_on else 0) — simple v1
    return max(ready, key=lambda n: urgency.get(n.goal_id or "", 0.5))
