"""ContextSection — the modular unit of agent context (architecture §9).

Instead of monolithic prompt templates, context is assembled from registered,
priority-ranked sections. The token budget trims lowest-priority sections first;
the KV-cache optimiser orders them stable→growing→volatile for prefix reuse.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Which agent a section is assembled for (architecture §9 scope column).
Scope = Literal["all_agents", "explorer_only", "verifier_only", "planner_only"]


def estimate_tokens(content: str) -> int:
    """Dependency-free token estimate (~4 chars/token).

    No tokenizer is installed, and pulling one in would violate YAGNI (principle
    1) — this heuristic is precise enough to drive progressive trimming and
    KV-cache accounting. Swap for a real tokenizer only if a backend needs exact
    counts.
    """
    return max(1, len(content) // 4)


@dataclass
class ContextSection:
    """One modular unit of agent context.

    priority:   higher = trimmed last by the token budget.
    scope:      which agent(s) this section is assembled for.
    token_cost: pre-computed; defaults to an estimate from the content length.
    """
    id: str
    priority: int
    scope: Scope
    content: str
    token_cost: int = 0

    def __post_init__(self) -> None:
        if not self.token_cost:
            self.token_cost = estimate_tokens(self.content)
