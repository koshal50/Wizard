"""Stage 4 — Packager (architecture §9).

Assembles authoritative investigation state into agent context. One source of
truth, two outputs:

  * build_explorer_packet(...)   → the exact trust-stripped dict agents already
                                    consume. Moved byte-for-byte from the loop's
                                    original _build_explorer_context so the running
                                    engine (MockExplorer / HttpExplorer) is unchanged.
  * build_explorer_sections(...) → the same material as modular, priority-ranked
                                    ContextSections that drive KV-cache ordering,
                                    token-budget trimming, and audit — and become
                                    the LLM prompt once a real backend is wired.

The packet keeps the engine working today; the sections deliver the Context
Engine philosophy for tomorrow. "Safe from both sides."

Compression rule (architecture: "summaries destroy causal history"): the kernel
keeps full Observations forever; only this projection to the agent is summarised.
No raw payloads, trust scores, or graph internals ever enter a section — that is
kernel invariant 3, the same boundary _build_explorer_context already enforced.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from wizard_kernel.context.sections import ContextSection
# Single source of truth for tool names (reuse, don't re-list) — invariant 5.
from wizard_kernel.world.tools import _REGISTERED_TOOLS

if TYPE_CHECKING:
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.contracts.node import InvestigationNode
    from wizard_kernel.contracts.observation import Observation
    from wizard_kernel.control.goals import GoalEngine
    from wizard_kernel.reality.observations import ObservationStore
    from wizard_kernel.session.budget import BudgetManager
    from wizard_kernel.session.investigation import Investigation

# How much recent history the volatile sections surface (compressed).
_RECENT_OBS_N = 5
_RECENT_FAIL_N = 3
# Claims at or above this belief score read as "verified"; below, "assumptions".
# Matches KnowledgeGraph.summary()'s own high-trust threshold — one source.
_VERIFIED_THRESHOLD = 0.6


class Packager:
    """Builds agent context packets and sections from the loop's own handles.

    Stateless: every method reads the handles passed in and returns a fresh
    projection. It never stores or mutates investigation state.
    """

    # ── Explorer: the exact contract agents consume (invariant 3) ───────────────

    def build_explorer_packet(
        self,
        inv: "Investigation",
        node: "InvestigationNode",
        goals: "GoalEngine",
        kg: "KnowledgeGraph",
        budget: "BudgetManager",
    ) -> dict:
        """The trust-stripped context dict handed to the Explorer Agent.

        Kept byte-for-byte compatible with the original loop._build_explorer_context
        so MockExplorer / HttpExplorer behaviour does not change. Agents never
        receive trust scores, raw KG relationships, or observation internals.
        """
        return {
            "investigation_id": inv.id,
            "intent": inv.intent,
            "targets": inv.targets,
            "current_node": {
                "id": node.id,
                "type": node.type,
                "action": node.action,
                "goal_id": node.goal_id,
            },
            "active_goals": [
                {"id": g.id, "name": g.name, "state": g.state}
                for g in goals.open_goals()
            ],
            "kg_summary": kg.summary(),
            "remaining_budget": budget.remaining,
        }

    # ── Explorer: the modular section view (KV cache / budget / audit) ──────────

    def build_explorer_sections(
        self,
        inv: "Investigation",
        node: "InvestigationNode",
        goals: "GoalEngine",
        kg: "KnowledgeGraph",
        budget: "BudgetManager",
        obs_store: "ObservationStore",
    ) -> list[ContextSection]:
        """Project the same state into priority-ranked ContextSections.

        IDs / priorities / scopes follow the built-in section table (architecture
        §9). Content is drawn only from existing handles and is compressed +
        trust-stripped, so nothing here widens what an agent can see beyond the
        packet above. `obs_store` is the one new handle the Packager needs (the
        volatile observation/failure sections); it is read-only.
        """
        summary = kg.summary()
        observations = obs_store.all()
        return [
            ContextSection(
                id="system_instructions", priority=100, scope="all_agents",
                content=self._system_instructions(inv, node),
            ),
            ContextSection(
                id="available_tools", priority=90, scope="explorer_only",
                content=self._available_tools(),
            ),
            ContextSection(
                id="repository_summary", priority=80, scope="all_agents",
                content=self._repository_summary(summary),
            ),
            ContextSection(
                id="verified_claims", priority=75, scope="explorer_only",
                content=self._verified_claims(summary),
            ),
            ContextSection(
                id="unverified_assumptions", priority=70, scope="explorer_only",
                content=self._unverified_assumptions(kg),
            ),
            ContextSection(
                id="recent_observations", priority=60, scope="explorer_only",
                content=self._recent_observations(observations),
            ),
            ContextSection(
                id="recent_failures", priority=50, scope="explorer_only",
                content=self._recent_failures(observations),
            ),
            ContextSection(
                id="budget_status", priority=40, scope="explorer_only",
                content=f"BUDGET: {budget.remaining} remaining",
            ),
        ]

    # ── Section renderers ───────────────────────────────────────────────────────
    # The engine node has no free-text description/hypothesis like the doc's
    # example; we map those to the concrete fields that DO exist (intent, node
    # type, planned action).

    @staticmethod
    def _system_instructions(inv: "Investigation", node: "InvestigationNode") -> str:
        return (
            "INVESTIGATION CONTEXT\n"
            "=====================\n"
            f"INTENT: {inv.intent}\n"
            f"TARGETS: {', '.join(inv.targets) if inv.targets else '(none)'}\n"
            f"NODE: {node.id} ({node.type})\n"
            f"ACTION: {node.action}\n\n"
            "INSTRUCTION: Return a single ToolRequest with tool, parameters, and reason."
        )

    @staticmethod
    def _available_tools() -> str:
        return "AVAILABLE TOOLS\n---------------\n" + "\n".join(sorted(_REGISTERED_TOOLS))

    @staticmethod
    def _repository_summary(summary: dict) -> str:
        high_trust = summary.get("high_trust_claims", [])
        lines = [f"{c['type']}:{c['key']} = {c['value']}" for c in high_trust]
        body = "\n".join(lines) if lines else "(no high-trust claims yet)"
        return (
            "REPOSITORY OVERVIEW\n-------------------\n"
            f"Claims known: {summary.get('claims_count', 0)}\n"
            f"{body}"
        )

    @staticmethod
    def _verified_claims(summary: dict) -> str:
        # Trust bucket comes through as the VERIFIED label; the raw score stays
        # kernel-side (invariant 3).
        high_trust = summary.get("high_trust_claims", [])
        body = "\n".join(
            f"VERIFIED: {c['type']}:{c['key']} = {c['value']}" for c in high_trust
        )
        return "VERIFIED KNOWLEDGE\n------------------\n" + (body or "(none yet)")

    @staticmethod
    def _unverified_assumptions(kg: "KnowledgeGraph") -> str:
        lines = [
            f"? {c.claim_type}:{c.key} = {c.value}"
            for c in kg.all_claims()
            if kg.trust_of(c.id) < _VERIFIED_THRESHOLD
        ]
        return "UNVERIFIED ASSUMPTIONS\n----------------------\n" + ("\n".join(lines) or "(none)")

    @classmethod
    def _recent_observations(cls, observations: list["Observation"]) -> str:
        lines = [cls._summarize_obs(o) for o in observations[-_RECENT_OBS_N:]]
        return "RECENT OBSERVATIONS\n-------------------\n" + ("\n".join(lines) or "(none)")

    @classmethod
    def _recent_failures(cls, observations: list["Observation"]) -> str:
        fails = [o for o in observations if (o.payload or {}).get("ok") is False]
        lines = [f"FAILED: {o.source_tool} → {cls._failure_reason(o)}" for o in fails[-_RECENT_FAIL_N:]]
        return "RECENT FAILURES\n---------------\n" + ("\n".join(lines) or "(none)")

    @staticmethod
    def _summarize_obs(obs: "Observation") -> str:
        payload = obs.payload or {}
        extra = f" exit={payload['exit_code']}" if "exit_code" in payload else ""
        return f"{obs.obs_type} via {obs.source_tool}: ok={payload.get('ok')}{extra}"

    @staticmethod
    def _failure_reason(obs: "Observation") -> str:
        payload = obs.payload or {}
        if payload.get("error"):
            return str(payload["error"])
        if payload.get("exit_code") is not None:
            return f"exit {payload['exit_code']}"
        return "unknown"
