"""
Runtime adapter interface.

The Runtime Engine is built by another developer/subsystem. This module
defines the *shape* of the boundary between Runtime and the Agent System
so integration doesn't require rewriting agent code. It intentionally
does not implement real repository execution.

Integration flow (see docs/runtime_integration.md for full detail):

    Runtime/Planner -> ExplorerInput -> ExplorerAgent -> ExplorerOutput
        -> Runtime executes the ToolRequest -> Observation
        -> Runtime updates Claims Graph -> VerificationInput
        -> VerificationAgent -> VerificationOutput
        -> Runtime writes verification_report.md
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.contracts.common import ToolRequest


class Observation(dict):
    """Placeholder type for what Runtime returns after executing a
    ToolRequest. The Agent System does not define this schema -- Runtime
    owns it -- but agents/tests need *some* concrete type to reference.
    Left as a permissive dict subclass so Runtime's real implementation
    can supply richer, Runtime-owned structure without the Agent System
    needing to change.
    """


class RuntimeExecutor(ABC):
    """Interface the Agent System expects a real Runtime Engine to satisfy.

    The Agent System never calls this against a real repository -- it is
    the contract Runtime must implement, and it's what the Agent System's
    own MockRuntimeExecutor (see mock_runtime.py) fulfils for local
    testing/examples.
    """

    @abstractmethod
    def execute(self, tool_request: ToolRequest) -> Observation:
        """Execute a Tool Request produced by Explorer and return an
        Observation. Only Runtime implementations may touch the
        repository/sandbox; the Agent System never calls real execution
        itself outside of test doubles.
        """
        raise NotImplementedError
