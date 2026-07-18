"""Investigation Graph — dynamic DAG of InvestigationNodes. Phase 3."""
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

    def set_state(
        self,
        node_id: str,
        state: NodeState,
        obs_ids: list[str] | None = None,
        claim_ids: list[str] | None = None,
    ) -> None:
        node = self._nodes[node_id]
        # InvestigationNode is a Pydantic model (not frozen) — use model_copy
        updates: dict = {"state": state}
        if obs_ids:
            updates["observation_ids"] = list(node.observation_ids) + obs_ids
        if claim_ids:
            updates["claim_ids"] = list(node.claim_ids) + claim_ids
        self._nodes[node_id] = node.model_copy(update=updates)

    def persist(self) -> None:
        fs_store.write(
            self._inv_id,
            "investigation_graph.json",
            [n.model_dump() for n in self._nodes.values()],
        )
