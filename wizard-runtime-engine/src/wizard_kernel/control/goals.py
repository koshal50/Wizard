"""Goal engine — checkpoint satisfaction. Phase 3+."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from wizard_kernel.storage import fs_store
from wizard_kernel.contracts.evidence import EvidenceCategory

if TYPE_CHECKING:
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph

log = logging.getLogger(__name__)

GoalState = Literal["open", "satisfied", "failed"]
_EVIDENCE_CATEGORIES = frozenset({
    "repository_read", "command_execution", "process_execution", "http_response", "runtime_startup", "http_readiness",
    "browser_navigation", "browser_observation", "browser_interaction", "browser_form_input", "docker_execution",
})


@dataclass
class Goal:
    id: str
    name: str
    required_claim_types: list[str]
    required_evidence: list[EvidenceCategory] = field(default_factory=list)
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

    def evidence_status(self, goal_id: str, observations: list) -> dict[str, list[str]]:
        goal = self._goals.get(goal_id)
        if not goal:
            return {"required": [], "completed": [], "missing": []}
        required = [r for r in goal.required_evidence if r in _EVIDENCE_CATEGORIES]
        completed = [r for r in required if any(
            obs.goal_id == goal.id and evidence_satisfies_requirement(obs, r)
            for obs in observations
        )]
        if 'http_readiness' in required and 'http_readiness' not in completed:
            from wizard_kernel.control.runtime_checks import readiness_observations
            if readiness_observations(observations, goal.id):
                completed.append('http_readiness')
        return {"required": required, "completed": completed,
                "missing": [r for r in required if r not in completed]}

    def evaluate_checkpoint(self, goal_id: str, kg: "KnowledgeGraph", observations: list | None = None) -> bool:
        """Re-evaluate a single goal against the current Knowledge Graph.

        Progress is updated fractionally: how many of the required claim types
        have at least one claim reaching the belief threshold.
        Returns True if the goal transitioned to satisfied.
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False

        if any(obs.goal_id == goal.id and not obs.success and obs.payload.get('required_check')
               for obs in observations or []):
            goal.progress = 0.0
            goal.state = 'open'
            return False
        if goal.state == 'satisfied':
            return True

        req_types = set(goal.required_claim_types)
        evidence = self.evidence_status(goal_id, observations or [])
        if not evidence["required"]:
            # Missing proof requirements are not proof.
            goal.progress = 0.0
            return False

        satisfied_types: set[str] = set()
        goal_observations = {getattr(obs, 'id', None) for obs in observations or [] if obs.goal_id == goal.id and obs.success}
        for claim in kg.all_claims():
            if claim.claim_type not in req_types:
                continue
            if not goal_observations or not any(ev.support_type == 'support' and goal_observations.intersection(ev.observation_ids)
                       for ev in kg.evidence_for(claim.id)):
                continue
            trust = kg.trust_of(claim.id)
            if trust < goal.belief_threshold:
                continue
            if goal.requires_execution_evidence and not kg.has_execution_evidence(claim.id):
                continue
            satisfied_types.add(claim.claim_type)

        claim_progress = len(satisfied_types) / len(req_types) if req_types else 1.0
        evidence_progress = len(evidence["completed"]) / len(evidence["required"]) if evidence["required"] else 1.0
        goal.progress = min(claim_progress, evidence_progress)
        if satisfied_types >= req_types and not evidence["missing"]:
            goal.state = "satisfied"
            goal.progress = 1.0
            return True
        return False

    def evaluate_all(self, kg: "KnowledgeGraph", observations: list | None = None) -> None:
        """Re-evaluate every open goal. Called after each node completes."""
        for g in self.all():
            self.evaluate_checkpoint(g.id, kg, observations)

    # ── Persistence ───────────────────────────────────────────────────────────

    def persist(self) -> None:
        """Write goal states to disk so they survive process restarts."""
        data = [
            {
                "id": g.id,
                "name": g.name,
                "required_claim_types": g.required_claim_types,
                "required_evidence": g.required_evidence,
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
                    required_evidence=item.get("required_evidence", []),
                    belief_threshold=item.get("belief_threshold", 0.6),
                    requires_execution_evidence=item.get("requires_execution_evidence", False),
                    state=item.get("state", "open"),
                    progress=item.get("progress", 0.0),
                )
            except Exception:  # noqa: BLE001
                log.warning("could not restore goal %s", item.get("id"), exc_info=True)

    # ── API projection ────────────────────────────────────────────────────────

    def to_api_list(self, observations: list | None = None) -> list[dict]:
        return [
            {"id": g.id, "name": g.name, "state": g.state, "status": _display_state(g.state),
             "progress": g.progress, **self.evidence_status(g.id, observations or [])}
            for g in self._goals.values()
        ]


def evidence_satisfies_requirement(observation, requirement: str) -> bool:
    """Match evidence from execution provenance, never from claim wording."""
    if requirement not in _EVIDENCE_CATEGORIES or not observation.success:
        return False
    return requirement in observation.evidence_categories


def evidence_categories_for_tool(tool: str, payload: dict) -> list[str]:
    """Classify evidence from the executed tool and its actual result."""
    if not payload.get("ok"):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    categories: list[str] = []
    if tool in {"read_file", "list_tree", "search_files", "path_exists"}:
        categories.append("repository_read")
    if tool == "execute_command" and payload.get("exit_code") == 0:
        categories.append("command_execution")
    if tool == "start_process" and data.get("is_running"):
        # Creation is not subsequent liveness/readiness evidence.
        categories.append("command_execution")
    if tool == "read_process" and data.get("is_running"):
        categories.append("process_execution")
        from wizard_kernel.control.runtime_checks import listening_url
        if listening_url(payload):
            categories.append('runtime_startup')
    if tool == "check_port" and data.get("active"):
        categories.append("process_execution")
    if tool == "http_request" and data.get("status_code") is not None:
        categories.append("http_response")
        from wizard_kernel.control.runtime_checks import readiness_failure
        if payload.get('readiness_check') and not readiness_failure(payload):
            categories.append('http_readiness')
    if tool == "browser_navigate":
        categories.append("browser_navigation")
    if tool in {"browser_snapshot", "browser_extract"}:
        categories.append("browser_observation")
    if tool in {"browser_click", "browser_type", "browser_back"}:
        categories.append("browser_interaction")
    if tool == "browser_type" and data.get("typed"):
        categories.append("browser_form_input")
    command = str((payload.get("meta") or {}).get("command", "")).lower()
    if (tool in {"execute_command", "start_process"}
            and re.search(r"\bdocker(?:[- ]compose|\s+compose)\b.*\bup\b", command)):
        categories.append("docker_execution")
    return list(dict.fromkeys(categories))


def _display_state(state: GoalState) -> str:
    return {"satisfied": "VERIFIED", "failed": "FAILED", "open": "UNVERIFIED / INCOMPLETE"}[state]
