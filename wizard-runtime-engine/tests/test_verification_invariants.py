from types import SimpleNamespace
from datetime import datetime, timezone
import sys

from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.claim import Claim
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.control.tool_validator import ToolRequestValidator
from wizard_kernel.control import loop
from wizard_kernel.context.packager import Packager
from wizard_kernel.reality.observations import ObservationStore
from wizard_kernel.session.budget import BudgetManager
from wizard_kernel.session.events import EventBus
from wizard_kernel.ports.goal_policy import goal_evidence_for
from wizard_kernel.world.sandbox.local import LocalProcessRuntime
from wizard_kernel.world.tools import ToolExecutor


class _StaticKG:
    def __init__(self, claim_type):
        self.claims = [Claim(id="c1", investigation_id="inv_test", claim_type=claim_type,
                             key="fact", value="observed",
                             created_at=datetime.now(timezone.utc))]

    def all_claims(self):
        return self.claims

    def trust_of(self, claim_id):
        return 0.99

    def has_execution_evidence(self, claim_id):
        return False


def test_empty_requirements_remain_open():
    engine = GoalEngine("inv_test")
    goal = Goal(id="g1", name="Unspecified", required_claim_types=[])
    engine.add(goal)
    assert engine.evaluate_checkpoint("g1", _StaticKG("FILE_READ")) is False
    assert goal.state == "open"


def test_static_file_evidence_cannot_satisfy_runtime_goal():
    reqs = goal_evidence_for("Start the Vite dev server and verify the signup page renders")
    assert reqs.requires_execution_evidence is True
    assert {"RUNTIME", "WEB"}.issubset(reqs.required_claim_types)
    engine = GoalEngine("inv_test")
    goal = Goal(id="g1", name="runtime page", required_claim_types=reqs.required_claim_types,
                requires_execution_evidence=True)
    engine.add(goal)
    assert engine.evaluate_checkpoint("g1", _StaticKG("WEB")) is False
    assert goal.state == "open"


def test_explorer_failure_does_not_create_tool_action():
    class FailedExplorer:
        def request(self, context):
            raise RuntimeError("provider disconnected")

    node = SimpleNamespace(id="n1", action={"tool": "read_file", "params": {"path": "README.md"}})
    validator = ToolRequestValidator(".")
    action = loop._resolve_tool_action(
        node, FailedExplorer(), {}, validator, BudgetManager(2), EventBus("inv_test")
    )
    assert action is None


def test_validated_tool_executes_and_becomes_observation(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("runtime result", encoding="utf-8")
    request = ToolRequest(tool="read_file", parameters={"path": "README.md"})
    validation = ToolRequestValidator(str(repo)).validate(request, 2)
    assert validation.valid
    sandbox = LocalProcessRuntime()
    sandbox.start(str(repo))
    try:
        result = ToolExecutor(sandbox, str(repo)).execute(
            {"tool": request.tool, "params": validation.sanitised_params}
        )
    finally:
        sandbox.stop()
    observations = ObservationStore("inv_test")
    obs = observations.append(node_id="n1", source_tool=request.tool,
                              obs_type="file_content", payload=result)
    assert obs.payload["data"]["content"] == "runtime result"


def test_execute_command_uses_sandbox_and_persists_execution_observation(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    command = f'"{sys.executable}" --version'
    request = ToolRequest(tool="execute_command", parameters={"command": command})
    validation = ToolRequestValidator(str(repo)).validate(request, 2)
    assert validation.valid
    sandbox = LocalProcessRuntime()
    sandbox.start(str(repo))
    try:
        result = ToolExecutor(sandbox, str(repo)).execute(
            {"tool": request.tool, "params": validation.sanitised_params}
        )
    finally:
        sandbox.stop()
    obs = ObservationStore("inv_process").append(
        node_id="n1", source_tool=request.tool, obs_type="command_result", payload=result
    )
    assert obs.payload["ok"] is True
    assert "Python" in obs.payload["stdout"]


def test_execution_observation_is_available_to_next_explorer_context():
    obs = SimpleNamespace(node_id="n1", source_tool="execute_command",
                          payload={"ok": True, "stdout": "server ready", "meta": {}})
    inv = SimpleNamespace(id="inv_test", intent="verify", targets=[], options={})
    node = SimpleNamespace(id="n2", type="execute", action={}, goal_id="g1")
    goals = SimpleNamespace(open_goals=lambda: [])
    kg = SimpleNamespace(summary=lambda: {})
    budget = SimpleNamespace(remaining=5)
    packet = Packager().build_explorer_packet(
        inv, node, goals, kg, budget, SimpleNamespace(all=lambda: [obs])
    )
    assert "server ready" in packet["previous_actions"][0]["outcome"]


def test_browser_disabled_runtime_goal_stays_unverified():
    reqs = goal_evidence_for("Verify dashboard page renders in the browser")
    engine = GoalEngine("inv_test")
    goal = Goal(id="g1", name="dashboard", required_claim_types=reqs.required_claim_types,
                requires_execution_evidence=reqs.requires_execution_evidence)
    engine.add(goal)
    # Repository evidence cannot stand in for the disabled browser/runtime plane.
    assert engine.evaluate_checkpoint("g1", _StaticKG("WEB")) is False
    assert goal.state == "open"


def test_compose_file_read_does_not_satisfy_compose_execution_goal():
    reqs = goal_evidence_for("Execute docker-compose up to start services")
    assert reqs.required_claim_types == ["DEPLOYMENT"]
    assert reqs.requires_execution_evidence is True
    engine = GoalEngine("inv_test")
    goal = Goal(id="g1", name="compose", required_claim_types=reqs.required_claim_types,
                requires_execution_evidence=True)
    engine.add(goal)
    assert engine.evaluate_checkpoint("g1", _StaticKG("DEPLOYMENT")) is False
    assert goal.state == "open"
