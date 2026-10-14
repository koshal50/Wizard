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


def test_validator_rejection_is_given_to_explorer_once_before_node_fails(tmp_path, monkeypatch):
    from wizard_kernel.contracts.agent import ExplorerResponse, ToolRequest
    from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
    from wizard_kernel.ports.agents import MockVerifier
    import wizard_kernel.ports.agents as agent_ports

    (tmp_path / "README.md").write_text("ready", encoding="utf-8")
    node = InvestigationNode(
        id="node_validation_feedback", type="read", action={},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
    )

    class Planner:
        def initial(self, *args, **kwargs):
            return TechnologyPlan(
                technologies=[TechnologyEntry(
                    name="Test goal", confidence="high", signals=["test"],
                    initial_goals=[GoalDefinition(
                        name="Test goal", required_claim_types=["FILESYSTEM"],
                        required_evidence=["repository_read"],
                    )],
                )],
                seed_nodes=[node],
            )

        def next_nodes(self, context):
            return []

        def interpret(self, node, obs):
            return []

    class Explorer:
        def __init__(self):
            self.contexts = []
            self.calls = 0

        def request(self, context):
            self.contexts.append(context)
            self.calls += 1
            request = (ToolRequest(tool="browser_snapshot", parameters={})
                       if self.calls == 1 else
                       ToolRequest(tool="read_file", parameters={"path": "README.md"}))
            return ExplorerResponse(investigation_id=context["investigation_id"],
                                    tool_request=request)

    explorer = Explorer()
    monkeypatch.setattr(agent_ports, "get_agents", lambda _options: (explorer, MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(
        repository_path=str(tmp_path), intent="investigate", targets=[],
        options={"budget": 4, "sandbox_mode": "local_dev"},
    ))
    kernel_loop.run(inv, manager, Planner())

    assert explorer.calls == 2
    # The Runtime associates this untagged seed node with a goal for evidence
    # ownership; both the first and corrective Explorer decision must receive
    # that same association instead of an unscoped/stale context.
    assert explorer.contexts[0]["current_node"]["goal_id"]
    assert explorer.contexts[1]["current_node"]["goal_id"] == explorer.contexts[0]["current_node"]["goal_id"]
    from wizard_kernel.control.investigation_graph import get_graph
    persisted_node = get_graph(inv.id).get(node.id)
    assert persisted_node.goal_id == explorer.contexts[0]["current_node"]["goal_id"]
    rejected = explorer.contexts[1]["previous_actions"][-1]
    assert rejected["tool"] == "browser_snapshot"
    assert rejected["succeeded"] is False
    assert "disabled" in rejected["outcome"]


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
    # The plan drained, but its legacy goal has no explicit evidence contract;
    # it must remain open and give the Planner the existing replan opportunity.
    assert planner.calls == ["next_nodes"]


def test_consecutive_failures_halt_before_budget_drains(tmp_path, monkeypatch):
    """A run that keeps failing stops at the failure guard, not at the budget.

    Without the guard, the Planner here would feed a fresh failing node forever
    and the loop would consume the whole (large) budget one gated step at a
    time. The guard must end it after `max_consecutive_failures` and still reach
    a terminal state with a report written — the mandate's "always finalize".
    """
    from wizard_kernel.contracts.agent import ExplorerResponse, ToolRequest
    from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
    from wizard_kernel.ports.agents import MockVerifier
    import wizard_kernel.ports.agents as agent_ports
    from wizard_kernel.storage import fs_store

    def _failing_node(i: int) -> InvestigationNode:
        return InvestigationNode(id=f"fail_{i}", type="read", action={},
                                 hypothesis=Hypothesis(kind=HypothesisKind.always_success))

    class Planner:
        _i = 0
        def initial(self, *a, **k):
            return TechnologyPlan(technologies=[], seed_nodes=[_failing_node(0)])
        def next_nodes(self, context):
            Planner._i += 1
            return [_failing_node(Planner._i)]
        def interpret(self, node, obs):
            return []

    class Explorer:
        def __init__(self): self.calls = 0
        def request(self, context):
            self.calls += 1
            # Reading a path that does not exist always fails (payload ok=False).
            return ExplorerResponse(
                investigation_id=context["investigation_id"],
                tool_request=ToolRequest(tool="read_file",
                                         parameters={"path": f"nope_{self.calls}.txt"}))

    explorer = Explorer()
    monkeypatch.setattr(agent_ports, "get_agents", lambda _o: (explorer, MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(
        repository_path=str(tmp_path), intent="investigate", targets=[],
        options={"budget": 40, "sandbox_mode": "local_dev",
                 "max_consecutive_failures": 3, "max_no_progress_steps": 99},
    ))
    kernel_loop.run(inv, manager, Planner())
    refreshed = manager.get(inv.id)

    assert refreshed.state == LifecycleState.incomplete
    # Halted at the guard (3), nowhere near the budget of 40.
    assert refreshed.nodes_completed <= 4, refreshed.nodes_completed
    # Finalization still ran: a report exists on disk.
    assert fs_store.read_text(inv.id, "verification_report.md")


def test_no_progress_halts_before_budget_drains(tmp_path, monkeypatch):
    """A run that completes nodes but never admits evidence stops at the
    no-progress guard rather than draining the budget."""
    from wizard_kernel.contracts.agent import ExplorerResponse, ToolRequest
    from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
    from wizard_kernel.ports.agents import MockVerifier
    import wizard_kernel.ports.agents as agent_ports

    (tmp_path / "a.txt").write_text("x", encoding="utf-8")

    def _node(i): return InvestigationNode(id=f"n_{i}", type="read", action={},
                                           hypothesis=Hypothesis(kind=HypothesisKind.always_success))

    class Planner:
        def initial(self, *a, **k):
            return TechnologyPlan(technologies=[], seed_nodes=[_node(0)])
        def next_nodes(self, context):
            Planner._i = getattr(Planner, "_i", 0) + 1
            return [_node(Planner._i)]
        def interpret(self, node, obs): return []

    class Explorer:
        def __init__(self): self.calls = 0
        def request(self, context):
            self.calls += 1
            # Reads succeed (ok=True) but a bare read of a tiny file admits no
            # claim for these template-less nodes → no progress.
            return ExplorerResponse(investigation_id=context["investigation_id"],
                                    tool_request=ToolRequest(tool="read_file",
                                                             parameters={"path": "a.txt"}))

    explorer = Explorer()
    monkeypatch.setattr(agent_ports, "get_agents", lambda _o: (explorer, MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(
        repository_path=str(tmp_path), intent="investigate", targets=[],
        options={"budget": 40, "sandbox_mode": "local_dev",
                 "max_no_progress_steps": 3, "max_consecutive_failures": 99},
    ))
    kernel_loop.run(inv, manager, Planner())
    refreshed = manager.get(inv.id)
    assert refreshed.nodes_completed <= 4, refreshed.nodes_completed
    assert refreshed.state in (LifecycleState.incomplete, LifecycleState.completed)


def test_planner_repeating_scheduled_work_cannot_spin_forever(tmp_path, monkeypatch):
    """The Planner proposing only already-scheduled nodes must terminate.

    This path consumes no budget (nothing executes), so before the replan guard
    it was a true infinite loop — the worst case of "repeatedly proposing
    equivalent work". The guard ends it after a bounded number of empty replans.
    """
    from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
    from wizard_kernel.ports.agents import MockExplorer, MockVerifier
    import wizard_kernel.ports.agents as agent_ports
    from wizard_kernel.storage import fs_store

    same = InvestigationNode(id="dup", type="read", action={"tool": "read_file", "params": {"path": "x"}},
                             hypothesis=Hypothesis(kind=HypothesisKind.always_success))

    class Planner:
        def initial(self, *a, **k):
            return TechnologyPlan(technologies=[], seed_nodes=[])
        def next_nodes(self, context):
            return [same]           # always the same already-scheduled node
        def interpret(self, node, obs):
            return []

    monkeypatch.setattr(agent_ports, "get_agents", lambda _o: (MockExplorer(), MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(
        repository_path=str(tmp_path), intent="investigate", targets=[],
        options={"budget": 40, "sandbox_mode": "local_dev",
                 "max_replans_without_new_work": 3},
    ))
    kernel_loop.run(inv, manager, Planner())   # must return, not hang
    refreshed = manager.get(inv.id)
    assert refreshed.state in (LifecycleState.incomplete, LifecycleState.completed)
    assert fs_store.read_text(inv.id, "verification_report.md")


def test_exception_path_still_finalizes_with_a_report(tmp_path, monkeypatch):
    """A fatal error inside the loop must still produce a report and a truthful
    terminal state, not a bare `failed` with nothing written."""
    from wizard_kernel.ports.agents import MockExplorer, MockVerifier
    import wizard_kernel.ports.agents as agent_ports
    from wizard_kernel.storage import fs_store

    class ExplodingPlanner:
        def initial(self, *a, **k):
            raise RuntimeError("boom in planning")
        def next_nodes(self, context): return []
        def interpret(self, node, obs): return []

    monkeypatch.setattr(agent_ports, "get_agents", lambda _o: (MockExplorer(), MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(
        repository_path=str(tmp_path), intent="investigate", targets=[],
        options={"budget": 5, "sandbox_mode": "local_dev"},
    ))
    kernel_loop.run(inv, manager, ExplodingPlanner())
    refreshed = manager.get(inv.id)

    assert refreshed.state == LifecycleState.failed
    assert "boom in planning" in (refreshed.error or "")
    # The whole point: a report exists despite the crash.
    assert fs_store.read_text(inv.id, "verification_report.md")


def test_finalize_is_idempotent(tmp_path, monkeypatch):
    """A normal completed run that is then finalized again keeps its state and
    does not rewrite a conflicting report."""
    from wizard_kernel.ports.agents import MockExplorer, MockVerifier
    import wizard_kernel.ports.agents as agent_ports
    from wizard_kernel.storage import fs_store
    from wizard_kernel.control import loop as L
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.control.investigation_graph import InvestigationGraph
    from wizard_kernel.control.goals import GoalEngine
    from wizard_kernel.reality.observations import ObservationStore
    from wizard_kernel.session import events as event_bus

    inv, manager = _run_sync()
    assert manager.get(inv.id).state == LifecycleState.completed
    before = fs_store.read_text(inv.id, "verification_report.md")

    # Call finalize again directly — must be a no-op (report already on disk).
    bus = event_bus.create(inv.id)
    L._finalize(inv, manager, InvestigationGraph(inv.id), KnowledgeGraph(inv.id),
                GoalEngine(inv.id), ObservationStore(inv.id), bus, error="late error")
    after = manager.get(inv.id)
    assert after.state == LifecycleState.completed   # not flipped to failed
    assert fs_store.read_text(inv.id, "verification_report.md") == before


def _obs_store_with(records, inv_id):
    """A real ObservationStore seeded with (tool, payload) records."""
    from wizard_kernel.reality.observations import ObservationStore
    store = ObservationStore(inv_id)
    for i, (tool, payload) in enumerate(records):
        store.append(node_id=f"n{i}", source_tool=tool,
                     obs_type="command_result", payload=payload, goal_id=None,
                     tool_request_id=None, execution_id=f"e{i}", evidence_categories=[])
    return store


def test_external_blocker_detects_failed_start(tmp_path):
    from wizard_kernel.control import loop as L
    store = _obs_store_with([
        ("execute_command", {"ok": False, "exit_code": 1,
                              "data": {"command": "npm run start"},
                              "stderr": "Invalid environment configuration:\n  - JWT_SECRET: Required"}),
    ], "inv_blk1")
    reason = L._external_blocker(store)
    assert reason and "did not start" in reason and "JWT_SECRET" in reason


def test_external_blocker_detects_dead_port(tmp_path):
    from wizard_kernel.control import loop as L
    store = _obs_store_with([
        ("start_process", {"ok": True, "data": {"command": "npm run start", "is_running": True}}),
        ("check_port", {"ok": True, "data": {"port": 4000, "active": False}}),
    ], "inv_blk2")
    reason = L._external_blocker(store)
    assert reason and "4000" in reason


def test_external_blocker_ignores_agent_failures(tmp_path):
    """A verifier/explorer seam failure is a Wizard problem, never 'blocked'."""
    from wizard_kernel.control import loop as L
    store = _obs_store_with([
        ("verifier", {"ok": False, "error": "Verifier request failed", "status_code": 422}),
        ("read_file", {"ok": True, "data": {}}),
    ], "inv_blk3")
    assert L._external_blocker(store) is None


def test_blocked_terminal_state_is_set_when_app_cannot_start(tmp_path, monkeypatch):
    """End-to-end through _finalize: a run whose only evidence is a failed app
    start, with an unmet runtime goal, finalizes as `blocked`, not `incomplete`."""
    from wizard_kernel.control import loop as L
    from wizard_kernel.contracts.status import LifecycleState
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.control.investigation_graph import InvestigationGraph
    from wizard_kernel.control.goals import GoalEngine, Goal
    from wizard_kernel.session import events as event_bus
    from wizard_kernel.storage import fs_store

    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(
        repository_path=str(tmp_path), intent="verify", targets=["runtime"],
        options={"budget": 5, "sandbox_mode": "local_dev"}))
    goals = GoalEngine(inv.id)
    goals.add(Goal(id="g1", name="Server starts", required_claim_types=["X"],
                   required_evidence=["execution"], belief_threshold=0.6,
                   requires_execution_evidence=True))
    store = _obs_store_with([
        ("execute_command", {"ok": False, "exit_code": 1,
                              "data": {"command": "npm run start"},
                              "stderr": "JWT_SECRET: Required"}),
    ], inv.id)
    bus = event_bus.create(inv.id)
    L._finalize(inv, manager, InvestigationGraph(inv.id), KnowledgeGraph(inv.id),
                goals, store, bus)
    refreshed = manager.get(inv.id)
    assert refreshed.state == LifecycleState.blocked, refreshed.state
    assert "JWT_SECRET" in refreshed.last_event
    assert fs_store.read_text(inv.id, "verification_report.md")


def test_extract_endpoint_reads_served_url_and_port():
    from wizard_kernel.control import loop as L
    assert L._extract_endpoint("VITE ready  Local: http://localhost:5173/") == ("http://localhost:5173", 5173)
    assert L._extract_endpoint("Local: http://localhost:\x1b[1m5173\x1b[22m/") == ("http://localhost:5173", 5173)
    assert L._extract_endpoints(
        "Local: http://localhost:\x1b[1m5173\x1b[22m/; API listening on http://localhost:4000"
    ) == [("http://localhost:5173", 5173), ("http://localhost:4000", 4000)]
    assert L._extract_endpoint("Server listening on port 4000") == ("http://localhost:4000", 4000)
    assert L._extract_endpoint("nothing useful here") == (None, None)


def test_probe_started_process_discovers_and_probes_endpoint(tmp_path):
    """After a server starts, the Runtime reads its output, extracts the URL it
    printed, and probes the port — recording real observations — so the endpoint
    becomes visible for the browser phase. No LLM involved."""
    from wizard_kernel.control import loop as L
    from wizard_kernel.contracts.agent import ToolRequest
    from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
    from wizard_kernel.control.tool_validator import ToolRequestValidator
    store = _obs_store_with([], "inv_probe1")
    node = InvestigationNode(id="start", type="execute", action={},
                             hypothesis=Hypothesis(kind=HypothesisKind.always_success))

    class FakeTools:
        def __init__(self): self.calls = []; self.ports = []
        def execute(self, action):
            self.calls.append(action["tool"])
            if action["tool"] == "read_process":
                return {"ok": True, "data": {"stdout_so_far":
                    "VITE Local: http://localhost:\x1b[1m5173\x1b[22m/; API listening on http://localhost:4000"}}
            if action["tool"] == "check_port":
                self.ports.append(action["params"]["port"])
                return {"ok": True, "data": {"port": action["params"]["port"], "active": True}}
            return {"ok": False}

    tools = FakeTools()
    validator = ToolRequestValidator(
        str(tmp_path), allowed_domains=["localhost"], browser_enabled=True,
    )
    url = L._probe_started_process(
        tools, store, node, "g1", {"meta": {"handle_id": "proc_1"}},
        validator=validator, attempts=3, delay=0,
    )
    assert url == "http://localhost:5173"
    assert "read_process" in tools.calls and "check_port" in tools.calls
    assert tools.ports == [5173, 4000]
    tools_seen = [o.source_tool for o in store.all()]
    assert "read_process" in tools_seen and "check_port" in tools_seen
    # Readiness updates validator prerequisites as well as persisted observations.
    # Without this, Runtime probes successfully but rejects the next navigation.
    result = validator.validate(
        ToolRequest(tool="browser_navigate", parameters={"url": url + "/"}),
        budget_remaining=10,
    )
    assert result.valid, result.reason


def test_probe_started_process_waits_for_late_endpoint_output(tmp_path):
    """Do not hand a live-but-still-starting process back as ready or repeat its start."""
    from wizard_kernel.control import loop as L
    from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
    store = _obs_store_with([], "inv_probe_late")
    node = InvestigationNode(id="start", type="execute", action={},
                             hypothesis=Hypothesis(kind=HypothesisKind.always_success))

    class FakeTools:
        def __init__(self): self.reads = 0; self.ports = []
        def execute(self, action):
            if action["tool"] == "read_process":
                self.reads += 1
                output = "starting child services" if self.reads == 1 else "Local: http://localhost:43127/"
                return {"ok": True, "data": {
                    "command": "run http://localhost:9999", "is_running": True,
                    "stdout_so_far": output,
                }}
            if action["tool"] == "check_port":
                self.ports.append(action["params"]["port"])
                return {"ok": True, "data": {"port": action["params"]["port"], "active": True}}
            return {"ok": False}

    tools = FakeTools()
    url = L._probe_started_process(
        tools, store, node, "g1", {"meta": {"handle_id": "proc_late"}},
        attempts=3, delay=0,
    )
    assert url == "http://localhost:43127"
    assert tools.reads == 2
    assert tools.ports == [43127]  # URL in the command itself is not readiness evidence.


def test_probe_started_process_gives_up_when_nothing_listens(tmp_path):
    from wizard_kernel.control import loop as L
    from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
    store = _obs_store_with([], "inv_probe2")
    node = InvestigationNode(id="start", type="execute", action={},
                             hypothesis=Hypothesis(kind=HypothesisKind.always_success))

    class FakeTools:
        def execute(self, action):
            if action["tool"] == "read_process":
                return {"ok": True, "data": {"stdout_so_far": "booting... http://localhost:5173"}}
            if action["tool"] == "check_port":
                return {"ok": True, "data": {"port": 5173, "active": False}}
            return {"ok": False}

    url = L._probe_started_process(FakeTools(), store, node, None,
                                   {"meta": {"handle_id": "p"}}, attempts=2, delay=0)
    # A printed URL is not readiness; no browser may use it until the listener
    # probe succeeds.
    assert url is None
    assert any(o.source_tool == "check_port" for o in store.all())


def test_external_blocker_is_none_when_app_was_reachable(tmp_path):
    """A stray dead-port probe (or a failed one-off command) must NOT mark a run
    `blocked` when the app actually answered elsewhere. Regression for
    inv_ecb34635cf1e: app served on :5173 (http_request ok) but the run was
    falsely blocked because the agent probed :80 once."""
    from wizard_kernel.control import loop as L
    store = _obs_store_with([
        ("start_process", {"ok": True, "data": {"command": "npm run dev", "is_running": True}}),
        ("http_request", {"ok": True, "data": {"url": "http://localhost:5173/", "status": 200}}),
        ("execute_command", {"ok": False, "exit_code": 1, "data": {"command": "docker compose up"}}),
        ("check_port", {"ok": True, "data": {"port": 80, "active": False}}),
    ], "inv_reach1")
    assert L._external_blocker(store) is None


def test_external_blocker_still_fires_when_nothing_reachable(tmp_path):
    """The gate must not swallow a genuine blocker: no reachable evidence at all."""
    from wizard_kernel.control import loop as L
    store = _obs_store_with([
        ("start_process", {"ok": True, "data": {"command": "npm run dev", "is_running": True}}),
        ("check_port", {"ok": True, "data": {"port": 5173, "active": False}}),
    ], "inv_reach2")
    assert L._external_blocker(store) and "5173" in L._external_blocker(store)


def test_external_blocker_names_crashed_background_server(tmp_path):
    """A server started OK but crashing later (seen only via read_process exit!=0)
    must be named with its real command + error, not a generic 'a start command'.
    Regression for inv_a2c9e5057dea (npm run dev → Cannot find module)."""
    from wizard_kernel.control import loop as L
    store = _obs_store_with([
        ("start_process", {"ok": True, "data": {"command": "npm run dev", "is_running": True}}),
        ("read_process", {"ok": True, "data": {"command": "npm run dev", "is_running": False,
                                               "exit_code": 1,
                                               "stderr_so_far": "Error: Cannot find module 'src/index.js'"}}),
    ], "inv_crash1")
    reason = L._external_blocker(store)
    assert reason and "npm run dev" in reason and "Cannot find module" in reason
    assert "a start command" not in reason


def test_external_blocker_ignores_a_running_background_server(tmp_path):
    """A read_process for a still-running server is not a crash."""
    from wizard_kernel.control import loop as L
    store = _obs_store_with([
        ("start_process", {"ok": True, "data": {"command": "npm run dev", "is_running": True}}),
        ("read_process", {"ok": True, "data": {"command": "npm run dev", "is_running": True,
                                               "exit_code": None}}),
        ("check_port", {"ok": True, "data": {"port": 5173, "active": False}}),
    ], "inv_crash2")
    # Not a crash blocker; falls through to the dead-port signal instead.
    reason = L._external_blocker(store)
    assert reason and "5173" in reason


def test_page_state_unwraps_page_observation_after_a_navigating_click():
    """After a click that changes the page, the planner must see the NEW page's
    controls — they live under data.page_observation, not top-level data. Without
    unwrapping, the planner kept planning against the pre-click (login) page and
    the run oscillated between links instead of filling the reached form.
    Regression for the 'clicked Create one then stuck' report."""
    from wizard_kernel.control.loop import _page_state
    from wizard_kernel.reality.observations import ObservationStore
    store = ObservationStore("inv_pagestate")
    # A click on the login page's "Create one" link that navigated to /register;
    # the resulting register form is nested under page_observation.
    store.append(
        node_id="n1", source_tool="browser_click", obs_type="browser_action",
        payload={"ok": True, "data": {
            "clicked": True, "selector": 'role=link[name="Create one"]',
            "url": "http://localhost:5173/register",
            "page_observation": {
                "url": "http://localhost:5173/register",
                "controls": [
                    {"role": "textbox", "name": "Email", "selector": 'role=textbox[name="Email"]',
                     "in_form": True, "form_index": 0},
                    {"role": "button", "name": "Create account",
                     "selector": 'role=button[name="Create account"]', "in_form": True, "form_index": 0},
                ],
            },
        }},
        goal_id=None, tool_request_id=None, execution_id="e1", evidence_categories=[])
    state = _page_state(store)
    assert state["page_url"] == "http://localhost:5173/register"
    names = [c["name"] for c in state["page_controls"]]
    assert names == ["Email", "Create account"]
    # The link that was clicked is recorded as acted.
    assert 'role=link[name="Create one"]' in state["interacted_selectors"]


def test_repeated_rejected_decisions_halt_before_budget_drains(tmp_path, monkeypatch):
    """Repeated validator rejections (a duplicate the Explorer keeps re-proposing)
    must trip the convergence guard, not drain the whole budget. Regression for
    inv_15dd1ad19304: 28 duplicate start_process/execute_command rejections ran a
    100-node budget for 9 minutes because decision-stage failures weren't counted."""
    from wizard_kernel.contracts.agent import ExplorerResponse, ToolRequest
    from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
    from wizard_kernel.ports.agents import MockVerifier
    import wizard_kernel.ports.agents as agent_ports
    from wizard_kernel.storage import fs_store

    (tmp_path / "a.txt").write_text("x", encoding="utf-8")

    def _node(i):
        return InvestigationNode(id=f"n_{i}", type="read", action={},
                                 hypothesis=Hypothesis(kind=HypothesisKind.always_success))

    class Planner:
        _i = 0
        def initial(self, *a, **k):
            return TechnologyPlan(technologies=[], seed_nodes=[_node(0)])
        def next_nodes(self, context):
            Planner._i += 1
            return [_node(Planner._i)]
        def interpret(self, node, obs): return []

    class Explorer:
        def request(self, context):
            # Always the identical read — executes once, then duplicate-rejected
            # by the validator on every subsequent node.
            return ExplorerResponse(investigation_id=context["investigation_id"],
                                    tool_request=ToolRequest(tool="read_file",
                                                             parameters={"path": "a.txt"}))

    monkeypatch.setattr(agent_ports, "get_agents", lambda _o: (Explorer(), MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(
        repository_path=str(tmp_path), intent="investigate", targets=[],
        options={"budget": 40, "sandbox_mode": "local_dev",
                 "max_consecutive_failures": 3, "max_no_progress_steps": 99}))
    kernel_loop.run(inv, manager, Planner())
    refreshed = manager.get(inv.id)
    # Halted at the guard, nowhere near the budget of 40.
    assert refreshed.nodes_completed <= 8, refreshed.nodes_completed
    assert fs_store.read_text(inv.id, "verification_report.md")


def test_start_declared_servers_starts_every_long_running_command(tmp_path):
    """A browser-operating run brings up the WHOLE app — both the client and the
    backend server it POSTs to — not whichever single serve command an agent
    picked. Regression for 'filled signup but no account': the backend wasn't up."""
    import json
    from wizard_kernel.control.loop import _start_declared_servers
    from wizard_kernel.reality.observations import ObservationStore
    from wizard_kernel.session import events as event_bus
    # Root serves the client (dev), a server workspace serves the backend (start).
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}}), encoding="utf-8")
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "package.json").write_text(
        json.dumps({"scripts": {"start": "node src/server.js"}}), encoding="utf-8")

    started = []
    class FakeTools:
        def execute(self, action):
            if action["tool"] == "start_process":
                started.append((action["params"]["command"], action["params"]["cwd"]))
                return {"ok": True, "data": {"handle_id": f"p{len(started)}", "is_running": True}}
            if action["tool"] == "read_process":
                return {"ok": True, "data": {"is_running": True, "stdout_so_far": "ready"}}
            return {"ok": True, "data": {}}

    store = ObservationStore("inv_bringup")
    _start_declared_servers(FakeTools(), store, str(tmp_path), event_bus.create("inv_bringup"), set())
    cmds = {c for c, _ in started}
    assert "npm run dev" in cmds and "npm run start" in cmds, started
