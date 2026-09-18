"""Loop integration test — end-to-end with MockPlanner, no real repo needed."""
import time
import threading
import pytest
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.contracts.plan import GoalDefinition, TechnologyEntry, TechnologyPlan
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.ports.planner import MockPlanner
from wizard_kernel.control import loop as kernel_loop


def _run_sync(repo_path: str = "/tmp", budget: int = 5) -> tuple:
    """Run loop synchronously (same thread) and return (inv, manager).

    The request is `investigate` with no target — the plainest run there is, and
    one whose goal (`Investigate Repository`) a directory with no key files can
    actually settle. The subject here is the loop, so it needs a run that can
    finish.

    It used to be `verify runtime`, which completed only because the built-in
    planner ignored the target and planned `Investigate Repository` in its place:
    a different goal, reported as success. Read as written, `verify runtime`
    against a directory with no runtime cannot be satisfied by anything, so under
    a planner that reads the command it correctly ends `incomplete` — see
    test_loop_reports_incomplete_when_goals_stay_open.
    """
    manager = InvestigationManager()
    req = InvestigationRequest(
        repository_path=repo_path,
        intent="investigate",
        targets=[],
        options={"budget": budget, "sandbox_mode": "local_dev"},
    )
    inv = manager.create(req)
    kernel_loop.run(inv, manager, MockPlanner())
    return inv, manager


def test_loop_reaches_completed():
    inv, manager = _run_sync()
    refreshed = manager.get(inv.id)
    assert refreshed is not None
    assert refreshed.state == LifecycleState.completed


def test_loop_budget_terminates():
    """Invariant 7: budget always terminates.

    Accepts `incomplete` because a starved budget may legitimately stop the run
    before the goals are met, and stopping early is not a crash. This asserts
    only that the loop *ends*; which terminal state it reaches at this budget is
    pinned by test_loop_reports_incomplete_when_goals_stay_open.
    """
    inv, manager = _run_sync(budget=1)
    refreshed = manager.get(inv.id)
    assert refreshed.state in (
        LifecycleState.completed,
        LifecycleState.incomplete,
        LifecycleState.failed,
    )
    assert refreshed.nodes_completed <= 1


class _UnsatisfiableGoalPlanner:
    """Declares one goal whose evidence nothing in this run can produce.

    No seed node and no follow-up nodes, so the loop has nothing to execute and
    cannot close the goal however long it runs.
    """

    def initial(self, manifest, intent, targets, options=None, question=""):
        # `question` is part of PlannerPort.initial: it is the user's sentence,
        # which the loop passes through so the planner can plan what was asked
        # rather than only what the command family implies.
        return TechnologyPlan(
            technologies=[TechnologyEntry(
                name="Stub", confidence="high", signals=["stub"],
                initial_goals=[GoalDefinition(
                    name="Verify Stub",
                    required_claim_types=["NOTHING_PRODUCES_THIS"],
                    belief_threshold=0.6,
                )],
                priority_files=[],
            )],
            seed_nodes=[],
        )

    def next_nodes(self, context):
        return []

    def interpret(self, node, obs):
        return []


def test_loop_reports_incomplete_when_goals_stay_open():
    """A run that stops with goals open is `incomplete`, never `completed`.

    Both used to report "complete", so a partial investigation read as a verified
    one — the whole point of the distinct state. `incomplete` is also terminal:
    the run ends here rather than looping (invariant 7).
    """
    manager = InvestigationManager()
    req = InvestigationRequest(
        repository_path="/tmp", intent="verify", targets=[],
        options={"budget": 5, "sandbox_mode": "local_dev"},
    )
    inv = manager.create(req)
    kernel_loop.run(inv, manager, _UnsatisfiableGoalPlanner())

    refreshed = manager.get(inv.id)
    assert refreshed.state == LifecycleState.incomplete
    # The event has to name *which* goals stayed open, or a reader cannot tell
    # what the run failed to establish.
    assert "Verify Stub" in refreshed.last_event
    assert "planner proposed no further steps" in refreshed.last_event


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


class _QuestionRecordingPlanner:
    """A conforming PlannerPort that records what `initial` was handed.

    Exists because the port's newest parameter is the easiest one to drop
    silently: a planner that never receives `question` still plans, still runs,
    and still produces a report — it just plans the command family instead of
    what the user asked, which is exactly the defect this field was added to
    fix. Nothing about the run's *outcome* reveals the loss, so the test has to
    look at the call itself.
    """

    def __init__(self) -> None:
        self.received: dict = {}

    def initial(self, manifest, intent, targets, options=None, question=""):
        self.received = {
            "intent": intent,
            "targets": list(targets),
            "question": question,
        }
        return TechnologyPlan(
            technologies=[TechnologyEntry(
                name="Stub", confidence="high", signals=["stub"],
                initial_goals=[GoalDefinition(
                    name="Verify Stub", required_claim_types=["NOTHING_PRODUCES_THIS"],
                )],
                priority_files=[],
            )],
            seed_nodes=[],
        )

    def next_nodes(self, context):
        return []

    def interpret(self, node, obs):
        return []


def test_the_users_sentence_reaches_the_planner():
    """The sentence the user typed is handed to the planner, verbatim.

    `intent` is the command family — one of four verbs — so before `question`
    existed the planner was told *which command* ran and never *what was asked*,
    and every run of a family planned identically however it was phrased.
    """
    planner = _QuestionRecordingPlanner()
    manager = InvestigationManager()
    asked = "why does the login form lose my session on refresh"
    req = InvestigationRequest(
        repository_path="/tmp", intent="investigate", targets=["architecture"],
        question=asked,
        options={"budget": 3, "sandbox_mode": "local_dev"},
    )
    inv = manager.create(req)
    kernel_loop.run(inv, manager, planner)

    assert planner.received["question"] == asked
    # And the family still travels as itself — the two are separate inputs, and
    # folding the sentence into `intent` would break the kernel's Literal typing.
    assert planner.received["intent"] == "investigate"
    assert planner.received["targets"] == ["architecture"]


def test_a_run_with_no_question_hands_the_planner_an_empty_string():
    """A menu-driven run asks nothing in words, and says so as "".

    Not None and not the family name: the planner has to be able to tell "the
    user typed nothing" from "the user typed something", and a fallback that
    substituted the family here would make every menu run look like a user who
    typed the word "explain".
    """
    planner = _QuestionRecordingPlanner()
    manager = InvestigationManager()
    req = InvestigationRequest(
        repository_path="/tmp", intent="report", targets=[],
        options={"budget": 3, "sandbox_mode": "local_dev"},
    )
    inv = manager.create(req)
    kernel_loop.run(inv, manager, planner)

    assert planner.received["question"] == ""
    assert planner.received["intent"] == "report"


class _ScriptedGoalPlanner:
    """One goal, closed by the first node, behind a chain of three.

    The shape of an interaction script: the Planner writes several steps, the
    FIRST one happens to produce the evidence its goal counts, and the rest are
    the remainder of what the run said it would do. The goal engine has no way to
    express "and the other four steps too" — it counts claim types, and one typed
    field satisfies the type — so the run only finishes the script if the loop
    does not stop at the moment the goal closes.
    """

    def __init__(self, files: list[str]) -> None:
        self._files = files
        self.calls: list[str] = []

    def _node(self, path: str, node_id: str, deps: list[str]):
        from wizard_kernel.contracts.node import (
            ClaimTemplate, Hypothesis, HypothesisKind, InvestigationNode,
        )
        return InvestigationNode(
            id=node_id,
            type="read",
            action={"tool": "read_file", "params": {"path": path, "max_bytes": 4096}},
            hypothesis=Hypothesis(kind=HypothesisKind.always_success),
            on_success=ClaimTemplate(claim_type="FILE_READ", key=path, value=True),
            depends_on=deps,
        )

    def initial(self, manifest, intent, targets, options=None, question=""):
        nodes = []
        previous: str | None = None
        for i, path in enumerate(self._files):
            node_id = f"step_{i}"
            nodes.append(self._node(path, node_id, [previous] if previous else []))
            previous = node_id
        return TechnologyPlan(
            technologies=[TechnologyEntry(
                name="Stub", confidence="high", signals=["stub"],
                initial_goals=[GoalDefinition(
                    name="Operate Stub", required_claim_types=["FILE_READ"],
                    requires_execution_evidence=False,
                )],
                priority_files=[],
            )],
            seed_nodes=nodes,
        )

    def next_nodes(self, context):
        self.calls.append("next_nodes")
        return []

    def interpret(self, node, obs):
        return []


def test_a_goal_closing_does_not_abandon_the_rest_of_the_plan(tmp_path):
    """Every step the Planner wrote runs, even though step one closes the goal.

    This is a live failure, not a hypothetical. Asked to log in and submit a
    sign-up form against a real dev server, the run typed into the first field,
    the single INTERACTION claim that produced closed "Operate Web Surface", and
    the loop stopped — with four steps of the script it had just written still
    queued, and a report claiming an operation on a form left half-filled.

    The failure is invisible from the outside: the run ends `completed`, with
    every goal satisfied, and the only trace of the six nodes it never executed
    is that they are still `waiting` in the persisted graph.
    """
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")

    planner = _ScriptedGoalPlanner(["a.txt", "b.txt", "c.txt"])
    manager = InvestigationManager()
    req = InvestigationRequest(
        repository_path=str(tmp_path), intent="investigate", targets=[],
        options={"budget": 10, "sandbox_mode": "local_dev"},
    )
    inv = manager.create(req)
    kernel_loop.run(inv, manager, planner)

    from wizard_kernel.control.investigation_graph import get_graph

    graph = get_graph(inv.id)
    states = {n.id: n.state for n in graph.all_nodes()}
    assert states == {"step_0": "complete", "step_1": "complete", "step_2": "complete"}, (
        "the loop stopped mid-plan: the goal closed on step one and the rest of "
        f"the script was abandoned — {states}"
    )
    assert manager.get(inv.id).nodes_completed == 3
    # Nothing extra was asked of the Planner to make this happen: the work was
    # already in the graph, so the drain is bounded by what was planned.
    assert planner.calls == []
