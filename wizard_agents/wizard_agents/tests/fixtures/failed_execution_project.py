"""Fixture data representing an investigation where the previously
requested execution step failed at Runtime, and the resulting claim has
no usable evidence."""
from __future__ import annotations

from app.contracts.common import PreviousAction, ToolName
from app.contracts.explorer import ExplorerInput, InvestigationNode, Route
from app.contracts.verification import ClaimInput, VerificationInput


def build_failed_execution_explorer_input() -> ExplorerInput:
    node = InvestigationNode(node_id="run_test_suite", goal="Determine whether the test suite passes")
    route = Route(node_order=[node.node_id], current_index=0)
    return ExplorerInput(
        investigation_id="inv-fixture-failed-exec",
        current_node=node,
        route=route,
        nodes=[node],
        previous_actions=[
            PreviousAction(
                node_id="run_test_suite",
                tool=ToolName.EXECUTE_COMMAND,
                parameters={"command": "pytest"},
                outcome="failed: command timed out",
                succeeded=False,
            )
        ],
    )


def build_failed_execution_verification_input() -> VerificationInput:
    claim = ClaimInput(claim_id="claim-tests-pass", statement="Test suite passes", evidence=[])
    return VerificationInput(investigation_id="inv-fixture-failed-exec", claims=[claim])
