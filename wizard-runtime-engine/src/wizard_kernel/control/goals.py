"""Goal engine — checkpoint satisfaction. Phase 3+."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from wizard_kernel.storage import fs_store

if TYPE_CHECKING:
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph

log = logging.getLogger(__name__)

GoalState = Literal["open", "satisfied", "failed"]


@dataclass
class Goal:
    id: str
    name: str
    required_claim_types: list[str]
    belief_threshold: float = 0.6
    requires_execution_evidence: bool = False
    state: GoalState = "open"
    progress: float = 0.0


class GoalEngine:
    def __init__(self, inv_id: str) -> None:
        self._inv_id = inv_id
        self._goals: dict[str, Goal] = {}

    def add(self, goal: Goal) -> None:
        self._goals[goal.id] = goal

    def get(self, goal_id: str) -> Goal | None:
        return self._goals.get(goal_id)

    def all(self) -> list[Goal]:
        return list(self._goals.values())

    def open_goals(self) -> list[Goal]:
        return [g for g in self._goals.values() if g.state == "open"]

    def all_satisfied(self) -> bool:
        return bool(self._goals) and all(
            g.state == "satisfied" for g in self._goals.values()
        )

    def mark_satisfied(self, goal_id: str) -> None:
        if goal_id in self._goals:
            self._goals[goal_id].state = "satisfied"
            self._goals[goal_id].progress = 1.0

    def evaluate_checkpoint(self, goal_id: str, kg: "KnowledgeGraph") -> bool:
        """Re-evaluate a single goal against the current Knowledge Graph.

        Progress is updated fractionally: how many of the required claim types
        have at least one claim reaching the belief threshold.
        Returns True if the goal transitioned to satisfied.
        """
        goal = self._goals.get(goal_id)
        if not goal or goal.state == "satisfied":
            return goal.state == "satisfied" if goal else False

        req_types = set(goal.required_claim_types)
        if not req_types:
            # A goal with no required types is automatically satisfied
            self.mark_satisfied(goal_id)
            return True

        satisfied_types: set[str] = set()
        for claim in kg.all_claims():
            if claim.claim_type not in req_types:
                continue
            trust = kg.trust_of(claim.id)
            if trust < goal.belief_threshold:
                continue
            if goal.requires_execution_evidence and not kg.has_execution_evidence(claim.id):
                continue
            satisfied_types.add(claim.claim_type)

        goal.progress = len(satisfied_types) / len(req_types)
        if satisfied_types >= req_types:
            goal.state = "satisfied"
            goal.progress = 1.0
            return True
        return False

    def evaluate_all(self, kg: "KnowledgeGraph") -> None:
        """Re-evaluate every open goal. Called after each node completes."""
        for g in list(self.open_goals()):
            self.evaluate_checkpoint(g.id, kg)

    # ── Persistence ───────────────────────────────────────────────────────────

    def persist(self) -> None:
        """Write goal states to disk so they survive process restarts."""
        data = [
            {
                "id": g.id,
                "name": g.name,
                "required_claim_types": g.required_claim_types,
                "belief_threshold": g.belief_threshold,
                "requires_execution_evidence": g.requires_execution_evidence,
                "state": g.state,
                "progress": g.progress,
            }
            for g in self._goals.values()
        ]
        try:
            fs_store.write(self._inv_id, "goals.json", data)
        except Exception:  # noqa: BLE001
            log.warning("goals persist failed for %s", self._inv_id, exc_info=True)

    def restore(self) -> None:
        """Load goal states from disk (called at startup for investigation restore)."""
        raw = fs_store.read(self._inv_id, "goals.json")
        if not isinstance(raw, list):
            return
        for item in raw:
            try:
                self._goals[item["id"]] = Goal(
                    id=item["id"],
                    name=item["name"],
                    required_claim_types=item.get("required_claim_types", []),
                    belief_threshold=item.get("belief_threshold", 0.6),
                    requires_execution_evidence=item.get("requires_execution_evidence", False),
                    state=item.get("state", "open"),
                    progress=item.get("progress", 0.0),
                )
            except Exception:  # noqa: BLE001
                log.warning("could not restore goal %s", item.get("id"), exc_info=True)

    # ── API projection ────────────────────────────────────────────────────────

    def to_api_list(self) -> list[dict]:
        return [
            {"id": g.id, "name": g.name, "state": g.state, "progress": g.progress}
            for g in self._goals.values()
        ]
