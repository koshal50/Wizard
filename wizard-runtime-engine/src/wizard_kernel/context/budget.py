"""Stage 6 — Token Budget + KV-cache ordering (architecture §11).

The architecture names this component "BudgetManager", but that name already
belongs to session.budget.BudgetManager — the tool-call budget and kernel
invariant 7. This is a DIFFERENT budget: the LLM context-window token budget.
It is named TokenBudget so it never clobbers the existing one; the tool-call
budget keeps flowing through the loop as `budget.remaining`, untouched.

Two responsibilities:
  * fit(...)            — progressive trimming: drop lowest-priority sections
                          until the total fits the context window.
  * optimize_order(...) — order sections stable → growing → volatile so the
                          model's KV cache reuses the unchanged prefix across
                          steps (the DeepSeek insight). Prefix caching is a
                          property of the serving layer, not of vLLM specifically
                          — vLLM, OpenAI-compatible servers, and local llama.cpp
                          all benefit — so this pays off no matter which backend
                          we settle on. "Safe from both sides."
"""
from __future__ import annotations

from wizard_kernel.context.sections import ContextSection

# KV-cache stability classes (architecture §11). Prefix-stable content first,
# volatile content last, so the identical prefix is reused every step.
_STABLE = frozenset({"system_instructions", "available_tools", "repository_summary"})
_GROWING = frozenset({"verified_claims"})              # appends only → prefix stable
_VOLATILE = frozenset({
    "unverified_assumptions", "recent_observations", "recent_failures",
    "budget_status", "budget_warning", "injected_context",
})


def _by_priority(group: list[ContextSection]) -> list[ContextSection]:
    return sorted(group, key=lambda s: -s.priority)


class TokenBudget:
    def __init__(
        self,
        max_context_tokens: int = 8192,
        reserved_output_fraction: float = 0.15,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.reserved_output_fraction = reserved_output_fraction

    def available(self) -> int:
        """Tokens usable for context after reserving room for the model's reply."""
        return int(self.max_context_tokens * (1 - self.reserved_output_fraction))

    def fit(self, sections: list[ContextSection]) -> list[ContextSection]:
        """Drop lowest-priority sections until the total fits `available()`.

        If everything already fits (the common case), the list is returned
        unchanged.
        """
        budget = self.available()
        total = sum(s.token_cost for s in sections)
        if total <= budget:
            return list(sections)

        kept = sorted(sections, key=lambda s: s.priority)  # ascending: lowest first
        while total > budget and kept:
            total -= kept.pop(0).token_cost
        return kept

    def optimize_order(self, sections: list[ContextSection]) -> list[ContextSection]:
        """Order stable → growing → volatile for maximum KV-cache prefix reuse.

        Within each group, higher priority comes first. Any section whose id is
        not classified is treated as most-volatile (placed last) so nothing is
        ever silently dropped.
        """
        stable = _by_priority([s for s in sections if s.id in _STABLE])
        growing = _by_priority([s for s in sections if s.id in _GROWING])
        volatile = _by_priority([s for s in sections if s.id in _VOLATILE])
        known = _STABLE | _GROWING | _VOLATILE
        other = _by_priority([s for s in sections if s.id not in known])
        return [*stable, *growing, *volatile, *other]

    def optimize_and_fit(self, sections: list[ContextSection]) -> list[ContextSection]:
        """Trim to the window, then KV-order the survivors.

        Which sections survive depends only on priority + token_cost, not on
        sequence — so fitting first and ordering second yields survivors that are
        always KV-ordered, even on the rare step where trimming occurs.
        """
        return self.optimize_order(self.fit(sections))
