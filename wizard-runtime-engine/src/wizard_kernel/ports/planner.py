"""Planner port — protocol + MockPlanner + HttpPlanner (Phase 6). Phase 3."""
from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from wizard_kernel.contracts.manifest import RepositoryManifest
from wizard_kernel.contracts.node import (
    ClaimTemplate, Hypothesis, HypothesisKind, InvestigationNode,
)
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.plan import TechnologyPlan, TechnologyEntry


@runtime_checkable
class PlannerPort(Protocol):
    def initial(
        self, manifest: RepositoryManifest, intent: str, targets: list[str]
    ) -> TechnologyPlan: ...

    def next_nodes(self, context: dict) -> list[InvestigationNode]: ...

    def interpret(
        self, node: InvestigationNode, obs: Observation
    ) -> list[InvestigationNode]: ...


# ── Mock Planner ──────────────────────────────────────────────────────────────

class MockPlanner:
    """Returns scripted responses — lets loop run end-to-end without real LLM."""

    def __init__(self, max_next_calls: int = 0) -> None:
        self._next_calls = 0
        self._max_next_calls = max_next_calls

    def initial(
        self, manifest: RepositoryManifest, intent: str, targets: list[str]
    ) -> TechnologyPlan:
        # Detect key files and produce a minimal deterministic plan
        signals = set(manifest.key_files)
        technologies: list[TechnologyEntry] = []
        seed_nodes: list[InvestigationNode] = []

        if "package.json" in signals:
            technologies.append(TechnologyEntry(
                name="Node.js", confidence="high",
                signals=["package.json"],
                initial_goals=["Verify Runtime", "Verify Dependencies"],
                priority_files=["package.json"],
            ))
            seed_nodes.append(_make_read_node("package.json", "goal_runtime"))

        if "requirements.txt" in signals or "pyproject.toml" in signals:
            technologies.append(TechnologyEntry(
                name="Python", confidence="high",
                signals=["requirements.txt"],
                initial_goals=["Verify Runtime", "Verify Dependencies"],
                priority_files=["requirements.txt"],
            ))
            seed_nodes.append(_make_read_node("requirements.txt", "goal_runtime"))

        if "Dockerfile" in signals:
            technologies.append(TechnologyEntry(
                name="Docker", confidence="high",
                signals=["Dockerfile"],
                initial_goals=["Verify Docker Build"],
                priority_files=["Dockerfile"],
            ))
            seed_nodes.append(_make_read_node("Dockerfile", "goal_docker"))

        if not technologies:
            # Unknown repo — add a generic discovery node
            technologies.append(TechnologyEntry(
                name="Unknown", confidence="low",
                signals=[], initial_goals=["Investigate Repository"],
                priority_files=[],
            ))
            seed_nodes.append(_make_discover_node())

        return TechnologyPlan(technologies=technologies, seed_nodes=seed_nodes)

    def next_nodes(self, context: dict) -> list[InvestigationNode]:
        if self._next_calls >= self._max_next_calls:
            return []
        self._next_calls += 1
        return []

    def interpret(
        self, node: InvestigationNode, obs: Observation
    ) -> list[InvestigationNode]:
        # Unexpected result — nothing to add in mock
        return []


# ── HTTP Planner (Phase 6) ────────────────────────────────────────────────────

class HttpPlanner:
    """Calls Yash's planner service via HTTP. Phase 6."""

    def __init__(self, base_url: str) -> None:
        self._url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict) -> dict:
        import httpx
        r = httpx.post(f"{self._url}{path}", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def initial(
        self, manifest: RepositoryManifest, intent: str, targets: list[str]
    ) -> TechnologyPlan:
        data = self._post("/plan/initial", {
            "manifest": manifest.model_dump(),
            "intent": intent,
            "targets": targets,
        })
        return TechnologyPlan.model_validate(data)

    def next_nodes(self, context: dict) -> list[InvestigationNode]:
        data = self._post("/plan/next", context)
        return [InvestigationNode.model_validate(n) for n in data.get("new_nodes", [])]

    def interpret(
        self, node: InvestigationNode, obs: Observation
    ) -> list[InvestigationNode]:
        data = self._post("/plan/interpret", {
            "node": node.model_dump(),
            "observation": obs.model_dump(),
        })
        return [InvestigationNode.model_validate(n) for n in data.get("new_nodes", [])]


# ── Factory ───────────────────────────────────────────────────────────────────

def get_planner(planner_url: str | None) -> PlannerPort:
    if planner_url:
        return HttpPlanner(planner_url)
    return MockPlanner()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _node_id() -> str:
    return f"node_{uuid.uuid4().hex[:6]}"


def _make_read_node(filename: str, goal_id: str) -> InvestigationNode:
    return InvestigationNode(
        id=_node_id(),
        type="read",
        action={"tool": "read_file", "params": {"path": filename, "max_bytes": 65536}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
        on_success=ClaimTemplate(
            claim_type="FILE_READ", key=filename, value=True,
        ),
        goal_id=goal_id,
    )


def _make_discover_node() -> InvestigationNode:
    return InvestigationNode(
        id=_node_id(),
        type="discovery",
        action={"tool": "list_tree", "params": {"max_depth": 3}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
        on_success=ClaimTemplate(
            claim_type="DISCOVERY", key="tree", value=True,
        ),
    )
