"""Loop integration test — end-to-end with MockPlanner, no real repo needed."""
import time
import threading
import pytest
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.ports.planner import MockPlanner
from wizard_kernel.control import loop as kernel_loop


def _run_sync(repo_path: str = "/tmp") -> tuple:
    """Run loop synchronously (same thread) and return (inv, manager)."""
    manager = InvestigationManager()
    req = InvestigationRequest(
        repository_path=repo_path,
        intent="verify",
        targets=["runtime"],
        options={"budget": 5, "sandbox_mode": "local_dev"},
    )
    inv = manager.create(req)
    planner = MockPlanner()
    kernel_loop.run(inv, manager, planner)
    return inv, manager


def test_loop_reaches_completed():
    inv, manager = _run_sync()
    refreshed = manager.get(inv.id)
    assert refreshed is not None
    assert refreshed.state == LifecycleState.completed


def test_loop_budget_terminates():
    """Invariant 7: budget always terminates."""
    manager = InvestigationManager()
    req = InvestigationRequest(
        repository_path="/tmp",
        intent="verify",
        targets=["runtime"],
        options={"budget": 1, "sandbox_mode": "local_dev"},
    )
    inv = manager.create(req)
    planner = MockPlanner()
    kernel_loop.run(inv, manager, planner)
    refreshed = manager.get(inv.id)
    assert refreshed.state in (LifecycleState.completed, LifecycleState.failed)
    assert refreshed.nodes_completed <= 1


def test_loop_two_investigations_isolated():
    """Invariant 6: investigations never share state."""
    manager = InvestigationManager()

    def run_one(path):
        req = InvestigationRequest(
            repository_path=path, intent="verify", targets=[],
            options={"budget": 3, "sandbox_mode": "local_dev"},
        )
        inv = manager.create(req)
        kernel_loop.run(inv, manager, MockPlanner())
        return inv.id

    id1 = run_one("/tmp/repo_a")
    id2 = run_one("/tmp/repo_b")

    inv1 = manager.get(id1)
    inv2 = manager.get(id2)
    assert inv1.repository_path != inv2.repository_path
    assert inv1.id != inv2.id


def test_agent_cannot_inject_trust():
    """Invariant 3: agent/planner responses cannot set trust directly."""
    from wizard_kernel.ports.agents import MockVerifier
    verifier = MockVerifier()
    # Even if a malicious agent includes a trust field
    fake_claims = [{"id": "cl_001", "trust": 0.99, "claim_type": "RUNTIME"}]
    result = verifier.assess(fake_claims)
    # MockVerifier returns assessment — trust field not on VerifierAssessment
    assert not hasattr(result, "trust")
    assert result.assessment in ("overall_sufficient", "needs_more_work")
