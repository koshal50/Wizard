from types import SimpleNamespace
from datetime import datetime, timezone
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.claim import Claim
from wizard_kernel.control.goals import (Goal, GoalEngine, evidence_categories_for_tool,
                                         evidence_satisfies_requirement)
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


def test_static_evidence_cannot_satisfy_runtime_categories():
    static = SimpleNamespace(success=True, evidence_categories=["repository_read"])
    for category in ("process_execution", "browser_navigation", "http_response", "docker_execution"):
        assert not evidence_satisfies_requirement(static, category)


def test_execution_tools_create_only_proven_categories():
    assert evidence_categories_for_tool("execute_command", {"ok": True, "exit_code": 0}) == ["command_execution"]
    assert evidence_categories_for_tool("start_process", {"ok": True, "data": {"is_running": True}}) == ["command_execution", "process_execution"]
    assert evidence_categories_for_tool("browser_navigate", {"ok": True}) == ["browser_navigation"]
    assert evidence_categories_for_tool("browser_snapshot", {"ok": True}) == ["browser_observation"]
    assert evidence_categories_for_tool("browser_click", {"ok": True}) == ["browser_interaction"]
    assert "browser_form_submission" not in evidence_categories_for_tool(
        "browser_click", {"ok": True, "data": {"clicked": True}}
    )
    assert set(evidence_categories_for_tool("browser_click", {
        "ok": True,
        "data": {"clicked": True, "submitted_form": True,
                 "page_observation": {"url": "http://local/", "snapshot": "form result"}},
    })) >= {"browser_interaction", "browser_form_submission"}
    assert evidence_categories_for_tool("browser_type", {"ok": True, "data": {"typed": True}}) == ["browser_interaction", "browser_form_input"]
    assert evidence_categories_for_tool("http_request", {"ok": True, "data": {"status_code": 200}}) == ["http_response"]
    assert evidence_categories_for_tool("read_file", {"ok": True, "data": {"status_code": 200}}) == ["repository_read"]


def test_docker_file_read_is_not_docker_execution():
    assert "docker_execution" not in evidence_categories_for_tool(
        "read_file", {"ok": True, "meta": {"path": "docker-compose.yml"}}
    )


def test_runtime_goal_policies_carry_required_evidence():
    assert set(goal_evidence_for("Start the Vite dev server and verify the signup page renders").required_evidence) >= {
        "process_execution", "browser_navigation", "browser_observation"
    }
    assert set(goal_evidence_for("Navigate to dashboard after authentication and confirm UI loads").required_evidence) >= {
        "browser_navigation", "browser_interaction", "browser_observation"
    }
    assert set(goal_evidence_for("Test sign up and log in using the observed form").required_evidence) >= {
        "browser_interaction", "browser_form_input", "browser_form_submission"
    }
    assert "browser_form_submission" in goal_evidence_for(
        "Verify that the Login component renders and can submit credentials"
    ).required_evidence
    assert set(goal_evidence_for("Launch backend and confirm it listens on port").required_evidence) >= {
        "process_execution", "http_response"
    }
    assert goal_evidence_for("Check authentication endpoints respond correctly").required_evidence == ["http_response"]
    assert set(goal_evidence_for("Verify that the Express server exposes authentication endpoints").required_evidence) == {
        "process_execution", "http_response"
    }
    assert goal_evidence_for("Check protected routes enforce authentication").required_evidence == ["http_response"]
    assert goal_evidence_for("Run ESLint to ensure code style compliance").required_evidence == ["command_execution"]
    assert set(goal_evidence_for("Run npm run dev to ensure Vite compiles").required_evidence) >= {
        "command_execution", "process_execution"
    }
    assert goal_evidence_for("Execute docker-compose up to start services").required_evidence == ["docker_execution"]
    assert set(goal_evidence_for("Verify that the Express application initializes without errors").required_evidence) == {
        "command_execution", "process_execution"
    }
    assert "docker_execution" in evidence_categories_for_tool(
        "start_process", {"ok": True, "data": {"is_running": True},
                          "meta": {"command": "docker compose up"}}
    )


def test_explorer_http_failure_preserves_safe_status_detail(monkeypatch):
    import httpx
    from wizard_kernel.ports.agents import HttpExplorer

    response = httpx.Response(
        422,
        json={"detail": "provider failed; OPENAI_API_KEY=do-not-leak"},
        request=httpx.Request("POST", "http://agents/agent/explorer"),
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)

    with pytest.raises(RuntimeError) as exc:
        HttpExplorer("http://agents/agent/explorer").request({"investigation_id": "inv"})

    assert "Explorer HTTP 422" in str(exc.value)
    assert "provider failed" in str(exc.value)
    assert "do-not-leak" not in str(exc.value)


def test_goal_requirements_are_required_even_with_claim_types():
    engine = GoalEngine("inv_test")
    goal = Goal(id="g1", name="unmapped", required_claim_types=["WEB"])
    engine.add(goal)
    assert not engine.evaluate_checkpoint("g1", _StaticKG("WEB"))
    assert goal.state == "open"


def test_goal_only_counts_compatible_evidence_associated_with_it():
    class RuntimeKG(_StaticKG):
        def has_execution_evidence(self, _claim_id):
            return True
    engine = GoalEngine("inv_test")
    goal = Goal(id="g1", name="server", required_claim_types=["RUNTIME"],
                required_evidence=["process_execution"], requires_execution_evidence=True)
    engine.add(goal)
    obs = SimpleNamespace(success=True, evidence_categories=["process_execution"], goal_id="other")
    assert not engine.evaluate_checkpoint("g1", RuntimeKG("RUNTIME"), [obs])
    obs.goal_id = "g1"
    assert engine.evaluate_checkpoint("g1", RuntimeKG("RUNTIME"), [obs])
    assert goal.state == "satisfied"


def test_observation_persists_execution_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path / "state"))
    obs = ObservationStore("inv_provenance").append(
        node_id="n1", source_tool="execute_command", obs_type="command_result",
        payload={"ok": True}, goal_id="g1", tool_request_id="tr1", execution_id="ex1",
        evidence_categories=["command_execution"],
    )
    assert (obs.investigation_id, obs.goal_id, obs.tool_request_id, obs.execution_id) == (
        "inv_provenance", "g1", "tr1", "ex1"
    )
    assert obs.evidence_categories == ["command_execution"]


def test_http_tool_uses_validator_executor_and_observation(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path / "state"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ready")
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/health"
        request = ToolRequest(tool="http_request", parameters={"url": url})
        validator = ToolRequestValidator(str(tmp_path), allowed_domains=["127.0.0.1"])
        port = ToolRequest(tool="check_port", parameters={
            "host": "127.0.0.1", "port": server.server_port,
        })
        port_result = ToolExecutor(None, str(tmp_path)).execute({
            "tool": "check_port", "params": port.parameters,
        })
        validator.record_execution("check_port", port.parameters, port_result)
        accepted = validator.validate(request, 1)
        assert accepted.valid
        result = ToolExecutor(None, str(tmp_path)).execute(
            {"tool": request.tool, "params": accepted.sanitised_params}
        )
        assert result["data"]["status_code"] == 200
        obs = ObservationStore("inv_http").append(
            node_id="n1", source_tool="http_request", obs_type="http_response",
            payload=result, goal_id="g1", tool_request_id="tr1", execution_id="ex1",
            evidence_categories=evidence_categories_for_tool("http_request", result),
        )
        assert evidence_satisfies_requirement(obs, "http_response")
    finally:
        server.shutdown()
        server.server_close()


def test_verifier_422_is_persisted_without_an_assessment(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path / "state"))
    class FailedVerifier:
        def assess(self, *_args):
            error = RuntimeError("unprocessable")
            error.response = SimpleNamespace(status_code=422)
            raise error
    class KG:
        def all_claims(self):
            return [SimpleNamespace(id="c1", claim_type="WEB", key="page", value="present")]
        def evidence_for(self, _claim_id):
            return []
    store = ObservationStore("inv_verifier_failure")
    loop._consult_verifier(
        SimpleNamespace(id="inv_verifier_failure"), FailedVerifier(), KG(), None,
        None, None, None, None, store, EventBus("inv_verifier_failure"), escalate=False,
    )
    observations = store.all()
    assert len(observations) == 1
    assert observations[0].obs_type == "agent_failure"
    assert observations[0].success is False
    assert observations[0].payload["status_code"] == 422


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
            error = RuntimeError("Explorer HTTP 422: Explorer output failed validation: invalid generated output")
            error.status_code = 422
            error.detail = "Explorer output failed validation: invalid generated output"
            error.request_id = "request-safe-id"
            raise error

    node = SimpleNamespace(id="n1", action={"tool": "read_file", "params": {"path": "README.md"}})
    validator = ToolRequestValidator(".")
    action, failure = loop._resolve_tool_action(
        node, FailedExplorer(), {}, validator, BudgetManager(2), EventBus("inv_test")
    )
    assert action is None
    assert failure == {
        "error_type": "EXPLORER_OUTPUT_INVALID",
        "status": 422,
        "detail": "Explorer output failed validation: invalid generated output",
        "provider_request_id": "request-safe-id",
        "model": "unknown",
    }


def test_validator_does_not_reaccept_identical_rejected_request(tmp_path):
    validator = ToolRequestValidator(str(tmp_path))
    invalid = ToolRequest(tool="browser_navigate", parameters={"url": "http://localhost"})
    first = validator.validate(invalid, 2)
    second = validator.validate(invalid, 2)
    assert not first.valid and "disabled" in first.reason
    assert not second.valid and "Duplicate rejected" in second.reason


def test_readiness_observations_can_be_repeated_after_world_state_changes(tmp_path):
    validator = ToolRequestValidator(str(tmp_path), allowed_domains=["127.0.0.1"])
    requests = [
        ToolRequest(tool="read_process", parameters={"handle_id": "proc-1"}),
        ToolRequest(tool="check_port", parameters={"host": "127.0.0.1", "port": 8123}),
        ToolRequest(tool="http_request", parameters={"url": "http://127.0.0.1:8123/", "method": "GET"}),
    ]
    for request in requests[:2]:
        assert validator.validate(request, 5).valid
        assert validator.validate(request, 5).valid

    validator.record_execution("check_port", requests[1].parameters, {
        "ok": True, "data": {"active": True, "host": "127.0.0.1", "port": 8123},
    })
    assert validator.validate(requests[2], 5).valid
    assert validator.validate(requests[2], 5).valid

    post = ToolRequest(tool="http_request", parameters={
        "url": "http://127.0.0.1:8123/", "method": "POST", "body": "{}",
    })
    assert validator.validate(post, 5).valid
    assert not validator.validate(post, 5).valid


def test_local_browser_and_http_require_observed_reachability(tmp_path):
    validator = ToolRequestValidator(
        str(tmp_path), allowed_domains=["127.0.0.1", "localhost"], browser_enabled=True,
    )
    nav = ToolRequest(tool="browser_navigate", parameters={"url": "http://localhost:43127/"})
    blocked = validator.validate(nav, 5)
    assert not blocked.valid and "RESOURCE_NOT_READY" in blocked.reason

    port = ToolRequest(tool="check_port", parameters={"host": "127.0.0.1", "port": 43127})
    assert validator.validate(port, 5).valid
    validator.record_execution("check_port", port.parameters, {
        "ok": True, "data": {"active": True, "host": "127.0.0.1", "port": 43127},
    })
    assert validator.validate(nav, 5).valid
    validator.record_execution("browser_navigate", nav.parameters, {"ok": True})
    assert validator.validate(ToolRequest(tool="browser_snapshot", parameters={}), 5).valid


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


def test_http_connection_failure_keeps_safe_target_without_success_evidence(monkeypatch):
    import wizard_kernel.world.tools as tools_module

    class RefusingOpener:
        def open(self, _request, timeout):
            raise OSError("connection refused")

    monkeypatch.setattr(tools_module, "build_opener", lambda *_args: RefusingOpener())
    executor = object.__new__(ToolExecutor)
    result = executor._tool_http_request(
        "http://user:password@127.0.0.1:8123/health?token=not-a-secret",
    )

    assert result["ok"] is False
    assert result["data"] == {
        "url": "http://127.0.0.1:8123/health",
        "method": "GET",
        "status_code": None,
    }
    assert "not-a-secret" not in str(result)
    assert "password" not in str(result)


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
