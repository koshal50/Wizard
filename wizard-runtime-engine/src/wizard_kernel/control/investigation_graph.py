"""InvestigationGraph — dynamic DAG of InvestigationNodes. Phase 3."""
from __future__ import annotations

from wizard_kernel.contracts.node import InvestigationNode, NodeState
from wizard_kernel.storage import fs_store


class InvestigationGraph:
    def __init__(self, inv_id: str) -> None:
        self._inv_id = inv_id
        self._nodes: dict[str, InvestigationNode] = {}

    def add(self, node: InvestigationNode) -> None:
        self._nodes[node.id] = node

    def get(self, node_id: str) -> InvestigationNode | None:
        return self._nodes.get(node_id)

    def all_nodes(self) -> list[InvestigationNode]:
        return list(self._nodes.values())

    def checkpoint_nodes(self) -> list[InvestigationNode]:
        return [n for n in self._nodes.values() if n.type == "checkpoint"]

    def get_ready_nodes(self, completed_ids: set[str]) -> list[InvestigationNode]:
        """All nodes whose dependencies are satisfied and that are still waiting."""
        return [
            n for n in self._nodes.values()
            if n.state == "waiting" and set(n.depends_on).issubset(completed_ids)
        ]

    def set_state(
        self,
        node_id: str,
        state: NodeState,
        obs_ids: list[str] | None = None,
        claim_ids: list[str] | None = None,
    ) -> None:
        node = self._nodes[node_id]
        updates: dict = {"state": state}
        if obs_ids:
            updates["observation_ids"] = list(node.observation_ids) + obs_ids
        if claim_ids:
            updates["claim_ids"] = list(node.claim_ids) + claim_ids
        self._nodes[node_id] = node.model_copy(update=updates)

    def mark_failed(
        self,
        node_id: str,
        obs_ids: list[str] | None = None,
    ) -> None:
        """Mark a node as failed — distinct from complete to preserve forensic accuracy.

        A failed node appears in the Investigation Graph with state='failed' so the
        report can show which investigation paths did not produce usable evidence.
        """
        self.set_state(node_id, "failed", obs_ids=obs_ids)

    def persist(self) -> None:
        fs_store.write(
            self._inv_id,
            "investigation_graph.json",
            [n.model_dump() for n in self._nodes.values()],
        )

    # ── Live read view ────────────────────────────────────────────────────────

    def frontier(self, limit: int = 8) -> dict:
        """What the investigation is doing now, and what it will do next.

        `persist()` only runs once, when the loop is already over, so mid-run the
        graph exists nowhere a surface can read. This is the live view: the node
        currently in ``running``, and the nodes still ``waiting``. It is a
        best-effort snapshot, not a consistent read — the loop thread rebinds
        dict entries (`_nodes[id] = node.model_copy(...)`) while this iterates, so
        a reader can observe two nodes mid-transition. That is the right trade for
        a progress view, and it is why nothing authoritative is derived from it.
        """
        nodes = list(self._nodes.values())
        running = [n for n in nodes if n.state == "running"]
        waiting = [n for n in nodes if n.state == "waiting"]
        return {
            "now": _node_view(running[0]) if running else None,
            "next": [_node_view(n) for n in waiting[:limit]],
            "counts": {
                "waiting": len(waiting),
                "running": len(running),
                "complete": sum(1 for n in nodes if n.state == "complete"),
                "failed": sum(1 for n in nodes if n.state == "failed"),
            },
        }


def _node_view(node: InvestigationNode) -> dict:
    """The fields a viewer needs to say what a node is about to do."""
    action = node.action or {}
    return {
        "node_id": node.id,
        "type": node.type,
        "tool": action.get("tool"),
        "params": action.get("params", {}),
        "goal_id": node.goal_id,
        "state": node.state,
    }


# ── Per-investigation registry ────────────────────────────────────────────────
# The loop owns its graph on a worker thread; the API runs on the server's. A
# surface that wants to show the current frontier therefore needs a handle on the
# live object, and this is the same registry pattern the browser subsystem uses
# (world/browser/__init__.py) for the same reason. Invariant 6 holds: one graph
# per investigation, keyed by id, never shared between runs.

_GRAPHS: dict[str, InvestigationGraph] = {}


def register_graph(inv_id: str, graph: InvestigationGraph) -> None:
    _GRAPHS[inv_id] = graph


def get_graph(inv_id: str) -> InvestigationGraph | None:
    return _GRAPHS.get(inv_id)

