"""Context Engine — read-only projection of investigation state into agent context.

The Context Engine never mutates state (kernel invariant 3). It reads the
authoritative handles the loop already owns (KnowledgeGraph, GoalEngine,
ObservationStore, BudgetManager, the current InvestigationNode) and projects
them into agent-specific context: a trust-stripped packet the agents consume
today, plus modular ContextSections that drive KV-cache ordering, token-budget
trimming, and audit (and become the LLM prompt once a real backend is wired).
"""
from wizard_kernel.context.engine import ContextBuildResult, ContextEngine
from wizard_kernel.context.sections import ContextSection, estimate_tokens

__all__ = ["ContextEngine", "ContextBuildResult", "ContextSection", "estimate_tokens"]
