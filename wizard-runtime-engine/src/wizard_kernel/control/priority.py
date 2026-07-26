"""Priority engine — picks next ready node. No LLM. No hardcoding.

Score = goal_urgency + uncertainty_gap - retry_penalty

- goal_urgency: supplied by the caller (e.g. 1.0 for unsatisfied goals)
- uncertainty_gap: prefer exploring claims we know least about
- retry_penalty: deprioritise nodes that previously failed
"""
from wizard_kernel.contracts.node import InvestigationNode


def next_ready(
    nodes: list[InvestigationNode],
    completed_ids: set[str],
    goal_urgency: dict[str, float] | None = None,
    kg_trust_by_goal: dict[str, float] | None = None,
) -> InvestigationNode | None:
    """Return the highest-priority ready node.

    A node is ready when:
    - state == "waiting"
    - all depends_on nodes are in completed_ids

    Args:
        nodes: all nodes in the investigation graph
        completed_ids: set of node IDs already completed or failed
        goal_urgency: goal_id -> urgency score (1.0 = unsatisfied, 0.0 = satisfied)
        kg_trust_by_goal: goal_id -> average trust of claims for that goal
    """
    urgency = goal_urgency or {}
    trust = kg_trust_by_goal or {}

    ready = [
        n for n in nodes
        if n.state == "waiting" and set(n.depends_on).issubset(completed_ids)
    ]
    if not ready:
        return None

    def score(n: InvestigationNode) -> float:
        gid = n.goal_id or ""
        goal_u = urgency.get(gid, 0.5)
        # Uncertainty gap: prefer nodes whose goal has low average trust
        avg_trust = trust.get(gid, 0.5)
        uncertainty_gap = 1.0 - avg_trust
        # Retry penalty: failed nodes get a lower score
        retry_penalty = 0.3 if n.state == "failed" else 0.0
        return goal_u + (0.3 * uncertainty_gap) - retry_penalty

    return max(ready, key=score)
