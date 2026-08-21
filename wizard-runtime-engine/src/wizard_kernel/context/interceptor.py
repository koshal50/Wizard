"""Stage 5 — Interceptor (architecture §10).

Gates agent INPUT — the assembled context — which is distinct from
ToolRequestValidator, the existing component that gates agent OUTPUT (the tool
request). Listeners may proceed, rewrite, or reject.

Ships with NO listeners on purpose (principle 1). Today the Packager already
trust-strips every section (invariant 3), the loop already halts before building
context once the budget is exhausted (invariant 7), and the validator already
fingerprints duplicate tool requests — so no default listener would have work to
do. The seam is built, wired, and tested, ready the moment a real input-side
policy is needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from wizard_kernel.context.sections import ContextSection

if TYPE_CHECKING:
    from wizard_kernel.contracts.node import InvestigationNode

InterceptAction = Literal["proceed", "rewrite", "reject"]


@dataclass
class InterceptResult:
    action: InterceptAction = "proceed"
    sections: list[ContextSection] | None = None   # populated on rewrite
    reason: str | None = None                       # populated on reject


class ContextListener(Protocol):
    def __call__(
        self,
        sections: list[ContextSection],
        node: "InvestigationNode | None",
        agent_type: str,
    ) -> InterceptResult: ...


class Interceptor:
    def __init__(self, listeners: list[ContextListener] | None = None) -> None:
        self._listeners = listeners or []

    def intercept(
        self,
        sections: list[ContextSection],
        node: "InvestigationNode | None",
        agent_type: str,
    ) -> InterceptResult:
        """Run listeners in order. First reject wins; rewrites chain."""
        current = sections
        for listener in self._listeners:
            result = listener(current, node, agent_type)
            if result.action == "reject":
                return result
            if result.action == "rewrite" and result.sections is not None:
                current = result.sections
        if current is not sections:
            return InterceptResult(action="rewrite", sections=current)
        return InterceptResult(action="proceed")
