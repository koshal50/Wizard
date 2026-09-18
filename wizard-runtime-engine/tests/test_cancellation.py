"""Cancellation is terminal — and reaches the loop wherever it lands.

The Runtime's cancel endpoint (DELETE /v1/investigations/{id}) writes the
`cancelled` state; the run loop only re-reads it once per node. So a cancel that
arrives while the loop is closing out its last node — the ordinary case for a
short investigation, and exactly when a user is most likely to hit Esc — used to
arrive at a loop that had already left the node loop, and the loop would then
generate a report and stamp `completed` over it. The client was told "cancelled",
polled, and was told "completed".

Two independent guards fix it, and both are tested here:

  * InvestigationManager.update refuses any transition out of a terminal state, so
    whichever of the two writers lands first is the answer.
  * The loop refuses to generate a report for a cancelled investigation, so the
    discarded run does not do the work either.
"""
from __future__ import annotations

import pytest

from wizard_kernel.contracts.plan import GoalDefinition, TechnologyEntry, TechnologyPlan
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.control import loop as kernel_loop
from wizard_kernel.ports.planner import MockPlanner
from wizard_kernel.session import events as event_bus
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store


def _new_investigation(manager: InvestigationManager, budget: int = 5):
    # `investigate` with no target, not `verify runtime`. The cancellation guards
    # are what this file tests, and `test_an_uncancelled_run_still_completes`
    # needs a run that can actually finish — which `verify runtime` against a
    # directory with no runtime cannot, once the planner reads the command rather
    # than ignoring it and planning a read-only goal in its place.
    req = InvestigationRequest(
        repository_path="/tmp",
        intent="investigate",
        targets=[],
        options={"budget": budget, "sandbox_mode": "local_dev"},
    )
    return manager.create(req)


def _report_exists(inv_id: str) -> bool:
    return (fs_store.inv_dir(inv_id) / "verification_report.md").exists()


# ── The manager's half ────────────────────────────────────────────────────────

@pytest.mark.parametrize("first", [LifecycleState.completed, LifecycleState.failed])
def test_a_cancel_cannot_overwrite_an_already_terminal_state(first):
    manager = InvestigationManager()
    inv = _new_investigation(manager)
    manager.update(inv.id, state=first)
    manager.update(inv.id, state=LifecycleState.cancelled, last_event="cancelled by user")
    assert manager.get(inv.id).state == first


def test_a_completion_cannot_overwrite_a_cancel():
    """The direction the Phase 4 end-to-end run actually hit."""
    manager = InvestigationManager()
    inv = _new_investigation(manager)
    manager.update(inv.id, state=LifecycleState.cancelled)
    manager.update(inv.id, state=LifecycleState.completed, last_event="complete")
    assert manager.get(inv.id).state == LifecycleState.cancelled


def test_a_refused_transition_does_not_apply_its_metadata():
    """Half-applying it would record a completed run as 'cancelled by user'."""
    manager = InvestigationManager()
    inv = _new_investigation(manager)
    manager.update(inv.id, state=LifecycleState.completed, last_event="complete")
    manager.update(inv.id, state=LifecycleState.cancelled, last_event="cancelled by user")
    assert manager.get(inv.id).last_event == "complete"


def test_updates_without_a_state_still_apply():
    """The loop's per-node edits must keep working on a running investigation."""
    manager = InvestigationManager()
    inv = _new_investigation(manager)
    manager.update(inv.id, nodes_completed=3, last_event="executing node_1")
    assert manager.get(inv.id).nodes_completed == 3


# ── The loop's half ───────────────────────────────────────────────────────────

class _CancelOnNextPlan:
    """Plans once, then cancels instead of planning again.

    This is the race in its exact shape: the cancel lands after the loop's last
    between-nodes check and before the report is written.
    """

    def __init__(self, manager: InvestigationManager, inv_id: str) -> None:
        self._manager = manager
        self._inv_id = inv_id
        self.next_nodes_calls = 0

    def initial(self, manifest, intent, targets, options=None, question=""):
        # `options` is part of PlannerPort.initial — the loop passes the
        # investigation's options through so a planner can decide whether to plan
        # a browser phase. This fake omitted it, so the loop's call raised
        # TypeError, the run went straight to `failed`, and the assertion that
        # failed here read "the loop never reached the cancel point" — the real
        # error hidden behind an assertion about a different thing.
        #
        # `question` is the user's sentence, the newest port parameter, and it
        # is here for the same lesson: a fake that omits a port parameter does
        # not fail where the omission is, it fails three assertions later under
        # a message about something else entirely.
        #
        # No seed nodes, and a goal nothing will ever satisfy, so the loop reaches
        # next_nodes() — where the cancel is injected.
        return TechnologyPlan(technologies=[
            TechnologyEntry(
                name="Python", confidence="high", signals=["pyproject.toml"],
                priority_files=[], seed_nodes=[],
                initial_goals=[GoalDefinition(name="Verify Runtime",
                                              required_claim_types=["RUNTIME"])],
            ),
        ], seed_nodes=[])

    def next_nodes(self, context):
        self.next_nodes_calls += 1
        self._manager.update(self._inv_id, state=LifecycleState.cancelled,
                             last_event="cancelled by user")
        return []


def test_a_cancel_arriving_at_the_end_of_the_loop_is_kept():
    manager = InvestigationManager()
    inv = _new_investigation(manager)
    planner = _CancelOnNextPlan(manager, inv.id)

    kernel_loop.run(inv, manager, planner)

    assert planner.next_nodes_calls == 1, "the loop never reached the cancel point"
    assert manager.get(inv.id).state == LifecycleState.cancelled


def test_a_cancelled_run_writes_no_report():
    """The discarded run must not do the work either — not just lose the label."""
    manager = InvestigationManager()
    inv = _new_investigation(manager)
    kernel_loop.run(inv, manager, _CancelOnNextPlan(manager, inv.id))

    assert not _report_exists(inv.id)
    emitted = [e.event_type for e in event_bus.get_recent_events(0, inv.id)]
    assert "report.generated" not in emitted
    assert "investigation.completed" not in emitted


def test_a_cancel_before_the_loop_starts_is_not_undone_by_the_run():
    """Run startup writes scanning/planning/loop states — none may revive it."""
    manager = InvestigationManager()
    inv = _new_investigation(manager)
    manager.update(inv.id, state=LifecycleState.cancelled, last_event="cancelled by user")

    kernel_loop.run(inv, manager, MockPlanner())

    assert manager.get(inv.id).state == LifecycleState.cancelled
    assert not _report_exists(inv.id)


def test_an_uncancelled_run_still_completes():
    """The guards must not stop the ordinary path from finishing."""
    manager = InvestigationManager()
    inv = _new_investigation(manager)

    kernel_loop.run(inv, manager, MockPlanner())

    assert manager.get(inv.id).state == LifecycleState.completed
    assert _report_exists(inv.id)


# ── The HTTP contract ─────────────────────────────────────────────────────────
#
# The DELETE route used to answer "cancelled" unconditionally, including when it
# had been refused — so the caller was told one thing by the cancel and the
# opposite by the next GET. The investigations are created straight through the
# manager here so no run loop is racing the assertion.

@pytest.fixture
def api():
    from fastapi.testclient import TestClient
    from wizard_kernel.api.app import app
    from wizard_kernel.api.deps import get_manager

    manager = InvestigationManager()
    app.dependency_overrides[get_manager] = lambda: manager
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client, manager
    app.dependency_overrides.clear()


def test_delete_reports_cancelled_when_the_cancel_wins(api):
    client, manager = api
    inv = _new_investigation(manager)

    body = client.delete(f"/v1/investigations/{inv.id}").json()

    assert body["status"] == "cancelled"
    assert body["cancelled"] is True
    assert manager.get(inv.id).state == LifecycleState.cancelled


def test_delete_reports_the_state_it_holds_when_the_cancel_loses(api):
    client, manager = api
    inv = _new_investigation(manager)
    manager.update(inv.id, state=LifecycleState.completed, last_event="complete")

    body = client.delete(f"/v1/investigations/{inv.id}").json()

    assert body["status"] == "completed"
    assert body["cancelled"] is False
    # And what it reports is what a following GET reports.
    assert client.get(f"/v1/investigations/{inv.id}").json()["status"] == body["status"]
    assert manager.get(inv.id).state == LifecycleState.completed


def test_delete_of_an_unknown_investigation_is_a_404(api):
    client, _ = api
    assert client.delete("/v1/investigations/inv_nope").status_code == 404
