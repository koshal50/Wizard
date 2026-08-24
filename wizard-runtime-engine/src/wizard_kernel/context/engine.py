"""ContextEngine — main orchestrator (architecture §22).

Composes the pipeline stages into one entry point, build_context(), that projects
authoritative kernel state into agent context. It is read-only: it never mutates
state (invariant 3). on_state_mutation() invalidates the cache so a stale
projection is never served after the graph, goals, or budget move.

Two architecture stages are intentionally folded in rather than built as separate
classes (principle 1 — no indirection without substance):
  * Reader (stage 1) + Compressor (stage 3) live inside the Packager — field
    selection is the invariant-3 filter; the last-N summary lines are the
    compression.
  * Injector (stage 5) is omitted until a producer of injected context exists.

build_context returns BOTH a `packet` (the trust-stripped dict agents consume
today — the exact _build_explorer_context contract) and `sections` (the modular
view that drives KV-cache ordering, token-budget trimming, and audit, and becomes
the LLM prompt once a real backend renders it). Keeping both is what makes the
engine safe for the current MockExplorer/HttpExplorer AND a future vLLM backend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from wizard_kernel.context.audit import ContextAudit
from wizard_kernel.context.budget import TokenBudget
from wizard_kernel.context.cache import ContextCache
from wizard_kernel.context.interceptor import Interceptor
from wizard_kernel.context.packager import Packager
from wizard_kernel.context.sections import ContextSection

if TYPE_CHECKING:
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.contracts.node import InvestigationNode
    from wizard_kernel.control.goals import GoalEngine
    from wizard_kernel.reality.observations import ObservationStore
    from wizard_kernel.session.budget import BudgetManager
    from wizard_kernel.session.events import EventBus
    from wizard_kernel.session.investigation import Investigation


@dataclass
class ContextBuildResult:
    sections: list[ContextSection] = field(default_factory=list)
    packet: dict = field(default_factory=dict)
    from_cache: bool = False
    rejected: bool = False
    reason: str | None = None


class ContextEngine:
    """Read-only projection engine. One per investigation (invariant 6)."""

    def __init__(
        self,
        bus: "EventBus",
        *,
        max_context_tokens: int = 8192,
        cache_size: int = 32,
        interceptor: Interceptor | None = None,
    ) -> None:
        self.packager = Packager()
        self.token_budget = TokenBudget(max_context_tokens=max_context_tokens)
        self.cache = ContextCache(max_size=cache_size)
        self.audit = ContextAudit(bus)
        self.interceptor = interceptor or Interceptor()

    # ── Main entry point (architecture §22 build_context) ───────────────────────

    def build_context(
        self,
        agent_type: str,
        inv: "Investigation",
        node: "InvestigationNode | None",
        goals: "GoalEngine",
        kg: "KnowledgeGraph",
        budget: "BudgetManager",
        obs_store: "ObservationStore",
    ) -> ContextBuildResult:
        node_id = node.id if node is not None else "global"

        # The packet is the agent contract — cheap, deterministic — always built.
        packet = self._build_packet(agent_type, inv, node, goals, kg, budget)

        # 1. Cache check (sections are the expensive part; they were already
        #    intercepted + fitted when stored).
        cached = self.cache.get(agent_type, node_id)
        if cached is not None:
            self.audit.record(agent_type, node_id, cached, from_cache=True)
            return ContextBuildResult(sections=cached, packet=packet, from_cache=True)

        # 2–4. Package into modular sections (Reader + Compressor folded in).
        sections = self._build_sections(agent_type, inv, node, goals, kg, budget, obs_store)

        # 6. Interceptor: proceed / rewrite / reject.
        result = self.interceptor.intercept(sections, node, agent_type)
        if result.action == "reject":
            self.audit.record(agent_type, node_id, [], rejected=True, reason=result.reason)
            return ContextBuildResult(packet=packet, rejected=True, reason=result.reason)
        if result.action == "rewrite" and result.sections is not None:
            sections = result.sections

        # 7. Token budget + KV-cache ordering.
        sections = self.token_budget.optimize_and_fit(sections)

        # 8. Cache.
        self.cache.set(agent_type, node_id, sections)

        # 9. Audit.
        self.audit.record(agent_type, node_id, sections, from_cache=False)

        return ContextBuildResult(sections=sections, packet=packet, from_cache=False)

    # ── Lifecycle ───────────────────────────────────────────────────────────────

    def on_state_mutation(self) -> None:
        """Invalidate cache when investigation state changes (§22)."""
        self.cache.invalidate()

    # ── Per-agent dispatch ──────────────────────────────────────────────────────
    # Explorer is the hot path (formalises loop._build_explorer_context). Verifier
    # and planner packagers land when their call sites are migrated — the seam is
    # explicit rather than silently returning empty context.

    def _build_packet(self, agent_type, inv, node, goals, kg, budget) -> dict:
        if agent_type == "explorer":
            return self.packager.build_explorer_packet(inv, node, goals, kg, budget)
        raise NotImplementedError(f"context packet for {agent_type!r} not built yet")

    def _build_sections(self, agent_type, inv, node, goals, kg, budget, obs_store):
        if agent_type == "explorer":
            return self.packager.build_explorer_sections(
                inv, node, goals, kg, budget, obs_store
            )
        raise NotImplementedError(f"context sections for {agent_type!r} not built yet")
