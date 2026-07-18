"""Goal engine — checkpoint satisfaction. Phase 3."""
from dataclasses import dataclass, field
from typing import Literal

GoalState = Literal["open", "satisfied", "failed"]


@dataclass
class Goal:
    id: str
    name: str
    required_claim_types: list[str]
    belief_threshold: float = 0.6
    requires_execution_evidence: bool = True  # verify goals need exec-tier evidence
    state: GoalState = "open"
    progress: float = 0.0


class GoalEngine:
    def __init__(self) -> None:
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
        return all(g.state == "satisfied" for g in self._goals.values())

    def mark_satisfied(self, goal_id: str) -> None:
        if goal_id in self._goals:
            self._goals[goal_id].state = "satisfied"
            self._goals[goal_id].progress = 1.0

    def to_api_list(self) -> list[dict]:
        return [
            {"id": g.id, "name": g.name, "state": g.state, "progress": g.progress}
            for g in self._goals.values()
        ]
