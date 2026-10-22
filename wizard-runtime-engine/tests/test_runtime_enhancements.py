"""Bounded enhancements through canonical Runtime boundaries; no paid providers."""
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.verification import Assertion, CheckSpec, RecoveryPlan, VerificationSpec
from wizard_kernel.control import checks, verification
from wizard_kernel.control.recovery import admit, next_ready
from wizard_kernel.context.selection import select, request_size
from wizard_kernel.ports.model import ModelFailure, prepare_context
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store
from wizard_kernel.world.tools import ToolExecutor


def obs(tool, data, *, goal="goal", success=True, **payload):
    return Observation(id="obs_" + str(id(data)), investigation_id="inv_enhance", node_id="node",
        goal_id=goal, source_tool=tool, obs_type="command_result", success=success,
        payload={"ok": success, "data": data, **payload}, created_at=datetime.now(UTC))


def check(field="exit_code", source="command", expected=0, **kwargs):
    return CheckSpec(id="goal", description="Verify actual outcome", assertions=[
        Assertion.model_validate({"field": field, "source": source, "operator": "equals", "expected": expected, **kwargs})])


def test_selection_fits_actual_serialized_request_and_protects_current_state():
    context = {"current_check": {"id": "goal"}, "available_tools": ["read_file"],
        "resource_state": {"browser": {"controls": [{"selector": "@e1"}]}},
        "recent_observations": [{"id": "old", "result": "x" * 5000}, {"id": "latest", "result": "actual failure"}],
        "knowledge": [{"old": "x" * 5000}], "missing_evidence": ["runtime"]}
    selected, audit = select(context, "system", {}, 1300)
    assert request_size(selected, "system", {}) <= 1300
    assert selected["resource_state"] == context["resource_state"]
    assert selected["recent_observations"] == [context["recent_observations"][-1]]
    assert selected["missing_evidence"] == ["runtime"]
    assert audit["omitted_sections"] and len(context["recent_observations"]) == 2
    assert select(selected, "system", {}, 1300)[0] == selected


def test_protected_context_overflow_fails_before_provider():
    with pytest.raises(ModelFailure) as error:
        prepare_context("planner", {"original_request": "x" * 50000}, VerificationSpec, 4000)
    assert error.value.kind == "context_budget"


@pytest.mark.parametrize("field,expected", [("visible", "true"), ("enabled", "true"), ("count", 1)])
def test_control_proofs_use_actual_named_controls(field, expected):
    criterion = check(field, "browser", expected, role="button", name="Continue")
    actual = obs("browser_snapshot", {"controls_complete": True, "controls": [
        {"role": "button", "name": "Continue", "visible": True, "enabled": True}]})
    assert checks.verdict(checks.evaluate(criterion, [actual])) == "passed"
    missing = obs("browser_snapshot", {"controls_complete": False, "controls": []})
    assert checks.verdict(checks.evaluate(criterion, [actual, missing])) == "unverified"


def test_json_proof_requires_complete_actual_response():
    criterion = check("json_value", "http", "true", json_pointer="/result/ok")
    actual = obs("http_request", {"url": "http://localhost/", "status_code": 200,
        "body_complete": True, "json_valid": True, "json_body": {"result": {"ok": True}}})
    assert checks.verdict(checks.evaluate(criterion, [actual])) == "passed"
    incomplete = obs("http_request", {"status_code": 200, "body_complete": False, "json_body": {"result": {"ok": True}}})
    assert checks.verdict(checks.evaluate(criterion, [incomplete])) == "unverified"


def test_new_navigation_invalidates_current_proof_not_stored_history():
    criterion = check("title", "browser", "Original")
    actual = obs("browser_snapshot", {"title": "Original"})
    historical = checks.evaluate(criterion, [actual])
    assert checks.verdict(historical) == "passed"
    mutation = obs("browser_navigate", {"url": "http://localhost/other"}, goal="other")
    assert checks.verdict(checks.evaluate(criterion, [actual, mutation])) == "unverified"
    assert checks.verdict(historical) == "passed"


def test_resource_death_and_failed_http_invalidate_current_compatible_proof():
    process = check("is_running", "process", "true")
    started = obs("start_process", {"handle_id": "owned", "is_running": True})
    stopped = obs("read_process", {"handle_id": "owned", "is_running": False}, goal="other")
    assert checks.verdict(checks.evaluate(process, [started, stopped])) == "unverified"
    http = check("status_code", "http", 200)
    response = obs("http_request", {"url": "http://localhost/", "status_code": 200})
    failed = obs("http_request", {"url": "http://localhost/", "status_code": None}, goal="other", success=False)
    assert checks.verdict(checks.evaluate(http, [response, failed])) == "unverified"


def test_truncated_text_cannot_prove_absence():
    criterion = CheckSpec(id="goal", description="No error", assertions=[Assertion.model_validate({
        "source": "browser", "field": "text", "operator": "not_contains", "expected": "Error"})])
    assert checks.verdict(checks.evaluate(criterion, [obs("browser_snapshot", {"text": "partial", "text_truncated": True})])) == "unverified"


def recovery_plan(**updates):
    data = {"reason": "Observed missing prerequisite", "observation_ids": ["observed"], "tasks": [
        {"goal_id": "goal", "check": {"id": "helper", "description": "Check documented prerequisite",
        "assertions": [{"source": "command", "field": "exit_code", "operator": "equals", "expected": 0}]}}]}
    data.update(updates)
    return RecoveryPlan.model_validate(data)


def test_recovery_admission_preserves_requirements_and_prioritizes_dependencies():
    original = VerificationSpec(checks=[check()])
    before = original.model_dump()
    merged, helpers, dependencies = admit(original, recovery_plan(), {}, [SimpleNamespace(id="observed")], capabilities={"command"})
    assert original.model_dump() == before
    assert merged.checks[0].assertions == original.checks[0].assertions
    assert dependencies == {"goal": ["helper"]}
    assert next_ready(merged.checks, {}).id == "helper"
    assert next_ready([merged.checks[0]], {"helper": {"status": "passed"}}).id == "goal"


@pytest.mark.parametrize("problem", ["unknown_proof", "cycle", "capability", "duplicate"])
def test_invalid_recovery_never_reaches_execution(problem):
    original = VerificationSpec(checks=[check()])
    plan = recovery_plan()
    capabilities = {"command"}
    if problem == "unknown_proof":
        plan.observation_ids = ["fabricated"]
    elif problem == "cycle":
        plan.tasks[0].check.depends_on = ["goal"]
    elif problem == "capability":
        capabilities = {"repository"}
    else:
        plan.tasks[0].check.description = original.checks[0].description
    with pytest.raises(ValueError):
        admit(original, plan, {}, [SimpleNamespace(id="observed")], capabilities=capabilities)


def command(*parts):
    return subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts)


def test_real_command_recovery_nodes_return_to_original_goal(tmp_path):
    verify_command = command(sys.executable, "verify_target.py")
    helper_command = command(sys.executable, "prepare_target.py")
    (tmp_path / "verify_target.py").write_text("from pathlib import Path\nraise SystemExit(0 if Path('ready').exists() else 1)")
    (tmp_path / "prepare_target.py").write_text("from pathlib import Path\nPath('ready').write_text('prepared')")
    (tmp_path / "README.md").write_text("Documented check: " + verify_command + "\nDocumented prerequisite: " + helper_command)
    class Policy:
        initial_attempts = 0
        recovery_calls = 0
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                if context.get("recovery_request"):
                    self.recovery_calls += 1
                    proof = context["recent_observations"][-1]["id"]
                    return model.model_validate(recovery_plan(observation_ids=[proof]).model_dump())
                return model.model_validate({"checks": [check().model_dump()]})
            goal = context["current_check"]["id"]
            if goal == "goal" and not context.get("recovery"):
                self.initial_attempts += 1
                if self.initial_attempts > 1:
                    return model.model_validate({"decision": {"kind": "blocked", "reason": "Documented prerequisite missing"}})
            entry = helper_command if goal == "helper" else verify_command
            return model.model_validate({"decision": {"kind": "tool", "reason": "Execute documented operation",
                "action": {"tool": "execute_command", "parameters": {"command": entry}}}})
    policy = Policy()
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", question="Verify the documented check and its prerequisite", options={"enable_recovery": True, "budget": 8}))
    verification.run(inv, manager, policy)
    saved = fs_store.read(inv.id, "verification.json")
    assert inv.state.value == "completed", saved
    assert policy.recovery_calls == 1
    assert saved["required_check_ids"] == ["goal"]
    assert saved["results"]["goal"]["status"] == "passed"
    assert saved["result_history"]["goal"]
    assert len([e for e in saved["executions"] if e["tool"] == "execute_command"]) == 3
    graph = fs_store.read(inv.id, "investigation_graph.json")
    assert next(n for n in graph if n["id"] == "check_goal")["depends_on"] == ["check_helper"]
    assert fs_store.read(inv.id, "recovery_plan.json")
    assert fs_store.read(inv.id, "plan.json")["checks"][0]["id"] == "goal"


def test_provider_failure_is_not_a_recovery_trigger(tmp_path):
    class Policy:
        planner_calls = 0
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                self.planner_calls += 1
                return model.model_validate({"checks": [check().model_dump()]})
            raise ModelFailure("http", "Rate limited", status=429)
    policy = Policy()
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", question="Verify operation", options={"enable_recovery": True}))
    verification.run(inv, manager, policy)
    assert policy.planner_calls == 1
    saved = fs_store.read(inv.id, "verification.json")
    assert saved["provider_status"] == 429 and not saved.get("recovery_attempted")


def test_screenshot_has_owner_artifact_and_private_capture_is_withheld(tmp_path):
    class Browser:
        started = True
        def screenshot(self, path):
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"test image")
        def page_view(self):
            return {"url": "http://localhost/"}
    tool = ToolExecutor(None, str(tmp_path), Browser(), investigation_id="inv_capture")
    result = tool.execute({"tool": "browser_screenshot"})
    assert result["ok"] and result["data"]["sha256"]
    assert (fs_store.inv_dir("inv_capture") / result["data"]["path"]).is_file()
    private = ToolExecutor(None, str(tmp_path), Browser(), investigation_id="inv_private", private_capture=True)
    assert not private.execute({"tool": "browser_screenshot"})["ok"]
    unowned = ToolExecutor(None, str(tmp_path), Browser())
    assert not unowned.execute({"tool": "browser_screenshot"})["ok"]


def test_recovery_permit_is_once_and_never_bypasses_command_policy(tmp_path):
    from wizard_kernel.control.tool_validator import ToolRequestValidator
    from wizard_kernel.contracts.agent import ToolRequest
    validator = ToolRequestValidator(str(tmp_path), [], False)
    action = ToolRequest(tool="execute_command", parameters={"command": command(sys.executable, "-V"), "cwd": "."})
    assert validator.validate(action, 3).valid
    assert not validator.validate(action, 3).valid
    assert validator.authorize_recheck(action, {"real-helper-proof"})
    assert validator.validate(action, 3).valid
    assert not validator.authorize_recheck(action, {"another-proof"})
    assert not validator.validate(action, 3).valid
    dangerous = ToolRequest(tool="execute_command", parameters={"command": "rm -rf /", "cwd": "."})
    assert validator.authorize_recheck(dangerous, {"proof"})
    assert not validator.validate(dangerous, 3).valid


def test_real_browser_and_http_proofs_with_owned_screenshot_and_artifact_api(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from fastapi.testclient import TestClient
    from wizard_kernel.api.app import create_app
    from wizard_kernel.api.deps import get_manager
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"ok":true}' if self.path == "/api" else b'<html><title>Proof fixture</title><button>Run proof</button></html>'
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if self.path == "/api" else "text/html")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    class Policy:
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                api = check("json_value", "http", "true", json_pointer="/ok").model_dump()
                api["id"] = "api"
                page = check("visible", "browser", "true", role="button", name="Run proof").model_dump()
                page.update(id="page", depends_on=["api"])
                return model.model_validate({"checks": [api, page]})
            resources = context["resource_state"]
            if context["current_check"]["id"] == "page" and not context["current_check"]["assertions"] and (resources["browser"] or {}).get("controls"):
                proof = next(o["id"] for o in reversed(context["recent_observations"]) if o["tool"] == "browser_snapshot")
                predicate = check("visible", "browser", "true", role="button", name="Run proof").assertions[0].model_dump()
                return model.model_validate({"decision": {"kind": "refine", "reason": "Use actual observed button", "refinement": {
                    "assertions": [predicate], "observation_ids": [proof]}}})
            if not resources["reachable_endpoints"]:
                tool, params = "check_port", {"host": "127.0.0.1", "port": server.server_port}
            elif context["current_check"]["id"] == "api":
                tool, params = "http_request", {"url": url + "api"}
            elif not resources["browser"]:
                tool, params = "browser_navigate", {"url": url}
            else:
                tool, params = "browser_snapshot", {}
            return model.model_validate({"decision": {"kind": "tool", "reason": "Observe actual fixture", "action": {"tool": tool, "parameters": params}}})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", targets=[url],
        question="Verify actual API and browser proof", options={"budget": 7, "screenshots": "checkpoints", "max_screenshots": 1,
        "allowed_domains": ["127.0.0.1"], "browser_headless": True}))
    try:
        verification.run(inv, manager, Policy())
        saved = fs_store.read(inv.id, "verification.json")
        assert inv.state.value == "completed", saved
        assert saved["results"]["page"]["status"] == "passed"
        assert saved["results"]["api"]["status"] == "passed"
        assert saved["cleanup"] == "Completed"
        capture = saved["artifacts"][0]
        file = fs_store.inv_dir(inv.id) / capture["path"]
        assert file.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        observation = next(json.loads(p.read_text("utf-8")) for p in (fs_store.inv_dir(inv.id) / "observations").glob("*.json")
            if json.loads(p.read_text("utf-8"))["id"] == capture["observation_id"])
        assert observation["obs_type"] == "artifact" and observation["execution_id"] == capture["execution_id"]
        app = create_app()
        app.dependency_overrides[get_manager] = lambda: manager
        client = TestClient(app)
        route = f"/v1/investigations/{inv.id}/report/artifacts/{inv.id}/"
        assert client.get(route + capture["path"]).content == file.read_bytes()
        assert client.get(route + "meta.json").status_code == 404
        assert client.get(route.replace(inv.id + "/screenshot", "foreign/screenshot") + "unlisted.png").status_code == 404
        assert "Captured screenshots" in fs_store.read_text(inv.id, "verification_report.md")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_cli_enhancements_are_explicit_and_default_off():
    from wizard.cli.models.investigation_request import RequestOptions
    assert "enable_recovery" not in RequestOptions.from_env({}).to_dict()
    options = RequestOptions.from_env({"WIZARD_RECOVERY": "1", "WIZARD_SCREENSHOTS": "on_failure"}).to_dict()
    assert options["enable_recovery"] is True and options["screenshots"] == "on_failure"
    assert not InvestigationRequest(repository_path=".", intent="verify").options.enable_recovery


def test_failure_capture_needs_executed_navigation_and_never_authorizes_interaction(tmp_path):
    from wizard_kernel.control.tool_validator import ToolRequestValidator
    from wizard_kernel.contracts.agent import ToolRequest
    validator = ToolRequestValidator(str(tmp_path), ["localhost"], True)
    screenshot = ToolRequest(tool="browser_screenshot", parameters={})
    assert not validator.validate(screenshot, 3).valid
    # A real execution may fail after starting Chromium. Passive diagnostic
    # capture is then legal; click/type remain gated on successful navigation.
    validator.record_execution("browser_navigate", {"url": "http://localhost/"}, {"ok": False})
    assert validator.validate(screenshot, 3).valid
    assert not validator.validate(ToolRequest(tool="browser_click", parameters={"selector": "@e1"}), 3).valid


def test_recovery_cannot_repeat_after_its_single_round(tmp_path):
    entry = command(sys.executable, "-c", "raise SystemExit(1)")
    helper = command(sys.executable, "-c", "print('checked prerequisite')")
    class Policy:
        recovery_calls = 0
        attempts = {}
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                if context.get("recovery_request"):
                    self.recovery_calls += 1
                    return model.model_validate(recovery_plan(observation_ids=[context["recent_observations"][-1]["id"]]).model_dump())
                return model.model_validate({"checks": [check().model_dump()]})
            goal = context["current_check"]["id"]
            phase = (goal, bool(context.get("recovery")))
            self.attempts[phase] = self.attempts.get(phase, 0) + 1
            if goal == "goal" and self.attempts[phase] > 1:
                return model.model_validate({"decision": {"kind": "blocked", "reason": "Actual command still fails"}})
            return model.model_validate({"decision": {"kind": "tool", "reason": "Observe actual command", "action": {
                "tool": "execute_command", "parameters": {"command": helper if goal == "helper" else entry}}}})
    policy = Policy()
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", question="Verify documented operation", options={"enable_recovery": True, "budget": 8}))
    verification.run(inv, manager, policy)
    saved = fs_store.read(inv.id, "verification.json")
    assert policy.recovery_calls == 1
    assert inv.state.value == "incomplete"
    assert saved["results"]["goal"]["status"] != "passed"
    assert len(saved["recovery_rechecks"]) == 1
