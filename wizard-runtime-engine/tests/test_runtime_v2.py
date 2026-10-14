"""Acceptance for the normal Runtime path; no provider requests."""
import json
import os
import shlex
import subprocess
import sys
import socket
from datetime import datetime, timezone

import pytest

from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.verification import CheckSpec, VerificationSpec
from wizard_kernel.control import checks, verification
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store


def _response(model, payload):
    """Test policies speak the actual canonical wire contract."""
    return model.model_validate({"decision": payload} if "decision" in model.model_fields else payload)


def test_event_persistence_recovers_windows_replace_contention(tmp_path, monkeypatch):
    from pathlib import Path
    from wizard_kernel.session.events import EventBus
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    original = Path.replace
    attempts = []
    def replace(path, target):
        attempts.append(path)
        if len(attempts) == 1:
            error = PermissionError("Temporary Windows sharing denial")
            error.winerror = 5
            raise error
        return original(path, target)
    monkeypatch.setattr(Path, "replace", replace)
    bus = EventBus("inv_contention")
    bus.emit("browser.page_observed", {"title": "Authenticated"})
    bus.emit("report.generated", {"report_path": "verification_report.md"})
    assert [e["seq"] for e in fs_store.read("inv_contention", "events.json")] == [1, 2]
    assert len(bus.get_recent_events()) == 2
    assert not list(fs_store.inv_dir("inv_contention").glob("*.tmp"))


def test_concurrent_event_writers_and_readers_preserve_complete_history(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from wizard_kernel.session.events import EventBus
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    bus = EventBus("inv_concurrent")
    def work(index):
        bus.emit("tool.executed", {"index": index})
        assert fs_store.read("inv_concurrent", "events.json")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, range(40)))
    saved = fs_store.read("inv_concurrent", "events.json")
    assert [e["seq"] for e in saved] == list(range(1, 41))
    assert {e["payload"]["index"] for e in saved} == set(range(40))
    assert len(bus.get_recent_events()) == 40


def test_auth_refinement_requires_page_discovery_and_browser_predicates():
    from pydantic import ValidationError
    from wizard_kernel.contracts.verification import decision_model, CheckRefinement
    payload = {"kind": "refine", "action": None, "reason": "Running process",
               "refinement": {"observation_ids": ["obs_process"], "assertions": [
                   {"source": "process", "field": "is_running", "operator": "equals", "expected": "true"}]}}
    before_page = decision_model(["browser_navigate"], allow_refine=False, browser_refinement=True)
    with pytest.raises(ValidationError):
        _response(before_page, payload)
    after_page = decision_model(["browser_snapshot"], browser_refinement=True)
    with pytest.raises(ValidationError):
        _response(after_page, payload)
    payload["refinement"]["assertions"] = [{"source": "browser", "field": "snapshot",
        "operator": "contains", "expected": "Account created", "after_submission": True}]
    decision = _response(after_page, payload)
    canonical = CheckRefinement.model_validate(decision.refinement.model_dump())
    assert canonical.assertions[0].source == "browser"
    assert canonical.assertions[0].after_submission


def test_planner_process_targets_are_declared_commands_not_component_labels():
    from wizard_kernel.contracts.verification import planning_model
    model = planning_model(["discovered-start-command"])
    payload = {"checks": [{"id": "startup", "description": "Verify actual startup", "capabilities": ["process"],
                          "assertions": [{"source": "process", "field": "is_running", "expected": "true", "target": "server"}]}]}
    with pytest.raises(ValueError):
        model.model_validate(payload)
    payload["checks"][0]["assertions"][0]["target"] = "discovered-start-command"
    result = VerificationSpec.model_validate(model.model_validate(payload).model_dump())
    assert result.checks[0].assertions[0].target == "discovered-start-command"
    payload["checks"][0]["assertions"][0]["target"] = ""
    assert model.model_validate(payload)


def test_process_refinement_cannot_use_observation_ids_or_http_fields_as_process_proof():
    from wizard_kernel.contracts.verification import decision_model
    model = decision_model(["read_process"], process_targets=["actual-command"])
    payload = {"kind": "refine", "reason": "Observe startup", "refinement": {"observation_ids": ["obs_running"],
        "assertions": [{"source": "process", "field": "is_running", "expected": "true", "target": "obs_running"}]}}
    with pytest.raises(ValueError):
        _response(model, payload)
    payload["refinement"]["assertions"] = [{"source": "http", "field": "body_preview", "operator": "equals", "expected": "true"}]
    with pytest.raises(ValueError):
        _response(model, payload)
    payload["refinement"]["assertions"] = [{"source": "process", "field": field, "expected": "true", "target": "actual-command"}
                                          for field in ("is_running", "active")]
    assert _response(model, payload).refinement


def test_browser_refinement_target_is_observed_url_not_expected_page_text():
    from wizard_kernel.contracts.verification import decision_model
    model = decision_model(["browser_snapshot"], browser_refinement=True, browser_targets=["http://localhost:12345/view"])
    payload = {"kind": "refine", "reason": "Observed outcome", "refinement": {
        "observation_ids": ["obs_result"], "assertions": [{"source": "browser", "field": "snapshot", "operator": "contains",
            "expected": "Signed in as", "target": "Signed in as", "after_submission": True}]}}
    with pytest.raises(ValueError):
        _response(model, payload)
    payload["refinement"]["assertions"][0]["target"] = ""
    assert _response(model, payload).refinement
    payload["refinement"]["assertions"][0]["target"] = "http://localhost:12345/view"
    assert _response(model, payload).refinement


def test_readback_schema_cannot_require_another_submission():
    from wizard_kernel.contracts.verification import decision_model
    model = decision_model(["browser_snapshot"], browser_refinement=True, require_submission=False)
    payload = {"kind": "refine", "reason": "Read back record", "refinement": {
        "observation_ids": ["obs_result"], "assertions": [{"source": "browser", "field": "text", "operator": "contains",
            "expected": "Created record", "after_submission": True}]}}
    with pytest.raises(ValueError):
        _response(model, payload)
    payload["refinement"]["assertions"][0]["after_submission"] = False
    assert _response(model, payload).refinement


def test_available_browser_discovery_cannot_be_declared_blocked():
    from pydantic import ValidationError
    from wizard_kernel.contracts.verification import decision_model
    from wizard_kernel.ports.model import strict_schema
    model = decision_model(["browser_navigate"], allow_refine=False, allow_evaluate=False, allow_blocked=False)
    schema = strict_schema(model)
    assert "BlockedDecision" not in schema.get("$defs", {})
    with pytest.raises(ValidationError):
        _response(model, {"kind": "blocked", "reason": "Unknown form fields", "action": None, "refinement": None})
    valid = _response(model, {"kind": "tool", "reason": "Inspect measured endpoint",
                             "action": {"tool": "browser_navigate", "parameters": {"url": "http://localhost:12345/"}}})
    assert valid.action.tool == "browser_navigate"
    # A genuine observed failure can still be reported when discovery is exhausted.
    fallback = decision_model(["read_process"], allow_refine=False)
    assert _response(fallback, {"kind": "blocked", "reason": "Process exited", "action": None}).kind == "blocked"


def observation(tool, data, **kwargs):
    return Observation(id="obs_test", investigation_id="inv_test", node_id="step", goal_id="check",
                       source_tool=tool, obs_type="command_result", created_at=datetime.now(timezone.utc),
                       success=True, payload={"ok": True, "data": data}, **kwargs)


@pytest.mark.parametrize("source,field,expected,tool,data", [
    ("http", "status_code", "200", "http_request", {"status_code": 500}),
    ("browser", "snapshot", "Authenticated", "browser_click", {"clicked": True}),
    ("process", "active", "true", "start_process", {"is_running": True}),
])
def test_an_operation_is_not_the_expected_outcome(source, field, expected, tool, data):
    check = CheckSpec(id="check", description="Expected behavior", assertions=[{
        "source": source, "field": field, "operator": "equals", "expected": expected}])
    assert checks.verdict(checks.evaluate(check, [observation(tool, data)])) != "passed"


def test_unsubmitted_login_page_cannot_prove_login():
    check = CheckSpec(id="check", description="Login succeeds", assertions=[{
        "source": "browser", "field": "snapshot", "operator": "contains",
        "expected": "Account", "after_submission": True}])
    assert checks.verdict(checks.evaluate(check, [observation("browser_snapshot", {"snapshot": "Account"})])) == "unverified"


def test_report_shows_matching_record_text_instead_of_only_page_header():
    from types import SimpleNamespace
    from wizard_kernel.contracts.status import LifecycleState
    title = "Unique created record"
    check = CheckSpec(id="check", description="Record appears", assertions=[{
        "source": "browser", "field": "text", "operator": "contains", "expected": title}])
    result = checks.evaluate(check, [observation("browser_snapshot", {"text": "Page header " * 300 + title})])
    assert title in result[0]["actual"]
    inv = SimpleNamespace(id="inv_test", question="Create record", intent="verify", targets=["runtime"], state=LifecycleState.completed)
    state = {"checks": [check.model_dump()], "results": {"check": {"status": "passed", "assertions": result}}, "model_calls": 0}
    report = verification._render(inv, state)
    observed = next(line for line in report.splitlines() if line.startswith("| Record appears")).split("|")[3]
    assert title in observed


def test_successful_form_fill_survives_snapshot_and_prevents_duplicate_batch():
    check = CheckSpec(id="check", description="Register", capabilities=["browser"], unresolved_reason="Discover result")
    page = {"url": "http://localhost/form", "snapshot": "Form", "controls": [{"selector": "@e1", "role": "textbox"},
        {"selector": "@e2", "role": "button", "submits_form": True}]}
    filled = observation("browser_fill_form", {"all_filled": True, "fields": [{"selector": "@e1", "typed": True}], "page_observation": page})
    snapshot = observation("browser_snapshot", page)
    resources = verification._resources([filled, snapshot])
    assert resources["form_state"]["all_filled"]
    tools = verification._available(check, resources, True, True)
    assert "browser_click" in tools and "browser_fill_form" not in tools
    clicked = observation("browser_click", {"submitted_form": True, "page_observation": page})
    assert verification._resources([filled, snapshot, clicked])["form_state"] is None


def test_auth_submit_requires_actual_filled_fields_but_navigation_is_allowed():
    check = CheckSpec(id="signup", description="Create an account", workflow="registration",
                      capabilities=["browser"], unresolved_reason="Discover result")
    page = {"controls": [
        {"selector": "@e1", "name": "Name", "role": "textbox", "filled": False, "required": False},
        {"selector": "@e2", "name": "Email", "role": "textbox", "filled": True},
        {"selector": "@e3", "name": "Create account", "role": "button", "submits_form": True},
        {"selector": "@e4", "name": "Create one", "role": "link"}]}
    assert "Name" in verification._form_submission_rejection(check, page, "@e3")
    assert verification._form_submission_rejection(check, page, "@e4") is None
    page["controls"][0]["filled"] = True
    assert verification._form_submission_rejection(check, page, "@e3") is None


def test_optional_record_field_does_not_block_submission():
    check = CheckSpec(id="record", description="Create record", workflow="form_submission",
                      capabilities=["browser"], unresolved_reason="Discover result")
    page = {"controls": [{"selector": "@e1", "name": "Optional date", "filled": False, "required": False},
                         {"selector": "@e2", "submits_form": True}]}
    assert verification._form_submission_rejection(check, page, "@e2") is None


def test_post_submission_progress_survives_recent_observation_window(tmp_path):
    from types import SimpleNamespace
    check = CheckSpec(id="check", description="Register", workflow="registration", capabilities=["browser"],
                      unresolved_reason="Discover outcome")
    before = observation("browser_snapshot", {"url": "http://localhost/form", "snapshot": "Registration form"}).model_copy(update={"id": "before"})
    submit = observation("browser_click", {"submitted_form": True, "page_observation": {
        "url": "http://localhost/result", "snapshot": "Account created"}}).model_copy(update={"id": "submitted"})
    later = [observation("browser_snapshot", {"url": "http://localhost/result", "snapshot": "Account created"}) for _ in range(4)]
    inv = SimpleNamespace(question="Register", intent="verify", targets=["runtime"], active_goals=[], budget_remaining=4)
    context = verification._context(inv, check, [], [before, submit, *later], ["browser_snapshot"], {}, {})
    progress = context["authentication_progress"]
    assert progress["submitted"] and progress["submission_observation_id"] == "submitted"
    assert progress["pre_submission_page"]["snapshot"] == "Registration form"
    assert "do not rediscover" in progress["next_objective"]
    assert progress["result_observation_ids"]
    changed = observation("browser_click", {"clicked": True, "page_observation": {"snapshot": "Another page"}})
    refreshed = verification._context(inv, check, [], [before, submit, *later, changed], ["browser_snapshot"], {}, {})
    assert refreshed["authentication_progress"]["result_observation_ids"] == []


def test_tactical_context_does_not_retransmit_full_repository_documents():
    from types import SimpleNamespace
    check = CheckSpec(id="check", description="Inspect observed UI", capabilities=["browser"], unresolved_reason="Discover result")
    inv = SimpleNamespace(question="Verify UI", intent="verify", targets=["runtime"], active_goals=[], budget_remaining=5)
    docs = [{"path": f"file_{i}.txt", "observation_id": f"obs_{i}", "content": "x" * 3000} for i in range(8)]
    page = observation("browser_snapshot", {"snapshot": "Observed form", "controls": []})
    context = verification._context(inv, check, [], [page], ["browser_snapshot"], {"documents": docs}, {})
    assert all(set(d) == {"path", "observation_id"} for d in context["discovery"]["documents"])
    assert len(json.dumps(context)) < 5000
    resources = verification._resources([page, observation("check_port", {"active": True, "host": "localhost", "port": 12345})])
    available = verification._available(check, resources, True, True)
    assert "browser_snapshot" in available and "read_file" in available
    assert "start_process" in available and "execute_command" not in available


def test_compact_schema_preserves_canonical_description_property():
    from wizard_kernel.ports.model import strict_schema
    schema = strict_schema(VerificationSpec)
    check = schema["$defs"]["CheckSpec"]
    assert "description" in check["properties"] and "description" in check["required"]
    assert check["properties"]["description"]["type"] == "string"
    assert "title" not in check


def test_observed_result_refinement_completes_without_another_model_call(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_TEST_DATA_JSON", json.dumps({"value": "disposable test"}))
    class PostSubmissionPolicy(RuntimePolicy):
        refined = False
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                return _response(model, {"checks": [{"id": "check", "description": "Submit and observe Complete",
                    "workflow": "registration", "capabilities": ["browser"], "unresolved_reason": "Discover submitted result"}]})
            assert not self.refined, "Already proven check must not request another decision"
            if context["authentication_progress"]["submitted"]:
                assert "browser_click" not in context["available_tools"]
                assert "browser_fill_form" not in context["available_tools"]
                if "Complete" not in (context["resource_state"]["browser"] or {}).get("snapshot", ""):
                    return _response(model, {"kind": "tool", "action": {"tool": "browser_snapshot", "parameters": {}}, "reason": "Observe submission result"})
                self.refined = True
                return _response(model, {"kind": "refine", "reason": "Requested outcome actually observed",
                    "refinement": {"observation_ids": [o["id"] for o in context["recent_observations"] if o["tool"].startswith("browser_")],
                        "assertions": [{"source": "browser", "field": "snapshot", "operator": "contains", "expected": "Complete", "after_submission": True}]}})
            # Only the test policy supplies dispatch scaffolding; Runtime's real
            # check stays unresolved until the actual submission result is seen.
            context = {**context, "current_check": {**context["current_check"], "assertions": ["pending outcome"]}}
            return super().request(role, context, model, **kwargs)
    policy = PostSubmissionPolicy(browser=True)
    inv, state = run_app(tmp_path, policy)
    assert policy.refined
    assert inv.state.value == "completed", state
    assert state["results"]["check"]["status"] == "passed"
    assert state["cleanup"] == "Completed"


def test_empty_and_cyclic_specifications_are_rejected():
    with pytest.raises(ValueError):
        VerificationSpec(checks=[])
    with pytest.raises(ValueError):
        CheckSpec(id="check", description="Missing expectation", assertions=[])


def test_bare_runtime_does_not_depend_on_static_discovery_or_extra_migration():
    spec = VerificationSpec(checks=[
        CheckSpec(id="discover", description="Find startup command", capabilities=["repository"],
                  assertions=[{"source": "repository", "field": "content", "operator": "equals", "expected": "run service"}]),
        CheckSpec(id="start", description="Start documented service", capabilities=["process"], depends_on=["discover"],
                  assertions=[{"source": "process", "field": f, "operator": "equals", "expected": "true"} for f in ("is_running", "active")]),
        CheckSpec(id="migration", description="Unrequested migration", depends_on=["start"],
                  assertions=[{"source": "command", "field": "exit_code", "operator": "equals", "expected": 0}])])
    verification._admit_plan(spec, {}, runtime_scope=True, default_runtime=True)
    assert [c.id for c in spec.checks] == ["start"]
    assert spec.checks[0].depends_on == []
    assert checks.verdict(checks.evaluate(spec.checks[0], [])) == "unverified"


def test_requested_browser_creation_cannot_keep_api_only_success_predicates():
    def goal(identity, workflow, depends=()):
        return CheckSpec(id=identity, description="Requested operation", workflow=workflow, capabilities=["http"],
            depends_on=list(depends), assertions=[{"source": "http", "field": "status_code", "operator": "equals", "expected": 201}])
    spec = VerificationSpec(checks=[goal("register", "registration"), goal("login", "login", ["register"]),
                                     goal("record", "general", ["login"])])
    verification._admit_plan(spec, {}, browser_scope=True)
    verification._account_dependencies(spec, True, login_requested=False)
    assert [c.id for c in spec.checks] == ["register", "record"]
    assert spec.checks[1].depends_on == ["register"]
    assert spec.checks[1].workflow == "form_submission"
    assert all(c.capabilities == ["browser"] and not c.assertions and c.unresolved_reason for c in spec.checks)
    assert all(checks.verdict(checks.evaluate(c, [])) == "unverified" for c in spec.checks)


def test_result_readback_does_not_require_creating_another_record():
    spec = VerificationSpec(checks=[
        CheckSpec(id="create", description="Create a record", workflow="form_submission", capabilities=["browser"], unresolved_reason="Discover form"),
        CheckSpec(id="readback", description="Verify that the created record appears in the list", workflow="form_submission",
                  capabilities=["browser"], depends_on=["create"], unresolved_reason="Observe result")])
    verification._admit_plan(spec, {})
    assert spec.checks[0].workflow == "form_submission"
    assert spec.checks[1].workflow == "general"
    assert spec.checks[1].depends_on == ["create"]


def test_json_http_body_uses_json_content_type(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from wizard_kernel.world.tools import ToolExecutor
    received = {}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received["type"] = self.headers.get("Content-Type")
            received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(201)
            self.end_headers()
            self.wfile.write(b'{"created":true}')
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        result = ToolExecutor(None, str(tmp_path)).execute({"tool": "http_request", "params": {
            "url": f"http://127.0.0.1:{server.server_port}/", "method": "POST", "body": json.dumps({"text": "test record"})}})
        assert result["ok"] and result["data"]["status_code"] == 201
        assert received == {"type": "application/json", "body": {"text": "test record"}}
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_submission_is_idempotent_and_owner_is_unique(tmp_path):
    manager = InvestigationManager()
    request = InvestigationRequest(repository_path=str(tmp_path), intent="verify", question="Run a check", idempotency_key="submission")
    first, second = manager.create(request), manager.create(request)
    assert first.id == second.id
    assert manager.claim_execution(first.id)
    assert not manager.claim_execution(first.id)


def test_command_only_non_node_discovery_populates_graphs_and_context(tmp_path):
    entry = command(sys.executable, "probe.py")
    (tmp_path / "README.md").write_text("Runtime verification command: " + entry, encoding="utf-8")
    (tmp_path / "probe.py").write_text("print('real runtime result')", encoding="utf-8")
    class ProjectPolicy:
        saw_discovery = False
        saw_knowledge = False
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                self.saw_discovery = any(entry in d["content"] for d in context["discovery"]["documents"])
                assert context["knowledge"] and "runtime" in context["targets"]
                return model.model_validate({"checks": [{"id": "runtime", "description": "Execute documented runtime check",
                    "assertions": [{"source": "command", "field": "exit_code", "operator": "equals", "expected": 0}]}]})
            self.saw_knowledge = bool(context["knowledge"])
            assert context["investigation_graph"]["current_goal"] == "runtime"
            return _response(model, {"kind": "tool", "reason": "Execute repository-documented command",
                "action": {"tool": "execute_command", "parameters": {"command": entry}}})
    policy = ProjectPolicy()
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", targets=["runtime"], options={"budget": 3}))
    verification.run(inv, manager, policy)
    saved = fs_store.read(inv.id, "verification.json")
    assert inv.state.value == "completed", saved
    assert policy.saw_discovery and policy.saw_knowledge
    kg = fs_store.read(inv.id, "knowledge_graph.json")
    graph = fs_store.read(inv.id, "investigation_graph.json")
    assert any(c["claim_type"] == "FILE_READ" for c in kg["claims"])
    assert any(e["source_tier"] == "execution" for evs in kg["evidence"].values() for e in evs)
    assert any(n["type"] == "read" and n["observation_ids"] and n["claim_ids"] for n in graph)
    assert any(n["action"].get("tool") == "execute_command" and n["observation_ids"] and n["claim_ids"] for n in graph)
    assert next(n for n in graph if n["id"] == "check_runtime")["state"] == "complete"
    from wizard_kernel.belief.trust import source_tier_for_tool
    assert source_tier_for_tool("http_request") == "execution"


def command(*args):
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


class RuntimePolicy:
    def __init__(self, browser=False):
        self.contexts = []
        self.browser = browser
    def request(self, role, context, model, **kwargs):
        if role == "planner":
            assertion = {"source": "browser", "field": "snapshot", "operator": "contains", "expected": "Complete", "after_submission": True} if self.browser else {
                "source": "http", "field": "status_code", "operator": "equals", "expected": "200"}
            return _response(model, {"checks": [{"id": "check", "description": "Actual application behavior", "assertions": [assertion]}]})
        self.contexts.append(context)
        state = context["resource_state"]
        if self.browser and not context["current_check"]["assertions"] and (state["browser"] or {}).get("controls"):
            return _response(model, {"kind": "refine", "action": None, "reason": "Use actual observed form and fixture contract",
                "refinement": {"observation_ids": [o["id"] for o in context["recent_observations"] if o["tool"] == "browser_snapshot"],
                "assertions": [{"source": "browser", "field": "snapshot", "operator": "contains",
                                "expected": "Complete", "after_submission": True}]}})
        if not state["processes"]:
            action = {"tool": "start_process", "parameters": {"command": command(sys.executable, "-u", "app.py")}}
        elif not self.browser:
            if any(o["tool"] == "http_request" for o in context["recent_observations"]):
                return _response(model, {"kind": "evaluate", "action": None, "reason": "Compare the real HTTP result"})
            endpoint = state["reachable_endpoints"][0]
            action = {"tool": "http_request", "parameters": {"url": f"http://{endpoint['host']}:{endpoint['port']}/"}}
        elif not state["browser"]:
            endpoint = state["reachable_endpoints"][0]
            action = {"tool": "browser_navigate", "parameters": {"url": f"http://{endpoint['host']}:{endpoint['port']}/"}}
        elif state["browser"].get("snapshot_required"):
            action = {"tool": "browser_snapshot", "parameters": {}}
        elif any(o["tool"] == "browser_click" for o in context["recent_observations"]):
            return _response(model, {"kind": "evaluate", "action": None, "reason": "Observe the submitted form's actual result"})
        elif "Complete" in state["browser"]["snapshot"]:
            return _response(model, {"kind": "evaluate", "action": None, "reason": "Compare the observed submission outcome"})
        elif any(o["tool"] == "browser_fill_form" for o in context["recent_observations"]):
            button = next(c for c in state["browser"]["controls"] if c.get("submits_form"))
            action = {"tool": "browser_click", "parameters": {"selector": button["selector"]}}
        else:
            inputs = [c for c in state["browser"]["controls"] if c["role"] == "textbox"]
            action = {"tool": "browser_fill_form", "parameters": {"fields": [
                {"selector": c["selector"], "value_ref": "value"} for c in inputs]}}
        return _response(model, {"kind": "tool", "action": action, "reason": ""})


def write_app(tmp_path):
    # Test target uses an OS-assigned port; no application assumptions in Runtime.
    (tmp_path / "app.py").write_text('''from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()
        self.wfile.write(b"<form onsubmit=\\"event.preventDefault();setTimeout(()=>document.body.innerHTML='Complete',300)\\"><label>Input<input required></label><input type='password' placeholder='Password' required><input type='password' placeholder='Password' required><button type='submit'>Send</button></form>")
server=HTTPServer(('127.0.0.1',0),Handler)
print(f'http://localhost:{server.server_port}',flush=True)
server.serve_forever()
''', encoding="utf-8")


def run_app(tmp_path, policy):
    write_app(tmp_path)
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify",
                         question="Verify actual application behavior", options={"budget": 8, "allowed_domains": ["localhost"]}))
    verification.run(inv, manager, policy)
    return inv, fs_store.read(inv.id, "verification.json")


def test_real_process_readiness_http_and_context_without_provider(tmp_path):
    policy = RuntimePolicy()
    inv, state = run_app(tmp_path, policy)
    assert inv.state.value == "completed", state
    assert state["results"]["check"]["status"] == "passed"


def test_component_label_target_is_grounded_before_dependent_http_check(tmp_path):
    entry = command(sys.executable, "-u", "app.py")
    class ComponentPolicy(RuntimePolicy):
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                return VerificationSpec.model_validate({"checks": [
                    {"id": "startup", "description": "Verify service startup", "capabilities": ["process"],
                     "assertions": [{"source": "process", "field": field, "operator": "equals", "expected": "true", "target": "service"}
                                    for field in ("is_running", "active")]},
                    {"id": "check", "description": "Verify response", "depends_on": ["startup"],
                     "assertions": [{"source": "http", "field": "status_code", "operator": "equals", "expected": "200"}]}]})
            if context["current_check"]["id"] == "startup":
                assert not context["current_check"]["assertions"]
                if not context["resource_state"]["processes"]:
                    return _response(model, {"kind": "tool", "reason": "Start discovered service",
                        "action": {"tool": "start_process", "parameters": {"command": entry}}})
                assert context["resource_state"]["reachable_endpoints"]
                return _response(model, {"kind": "refine", "reason": "Bind readiness to actual observed execution",
                    "refinement": {"observation_ids": [o["id"] for o in context["recent_observations"]],
                        "assertions": [{"source": "process", "field": field, "operator": "equals", "expected": "true", "target": entry}
                                       for field in ("is_running", "active")]}})
            return super().request(role, context, model, **kwargs)
    inv, state = run_app(tmp_path, ComponentPolicy())
    assert inv.state.value == "completed", state
    assert state["results"]["startup"]["status"] == "passed"
    assert state["results"]["check"]["status"] == "passed"
    assert [e["tool"] for e in state["executions"]] == ["start_process", "http_request"]
    assert all(a["assertion"]["target"] == entry for a in state["results"]["startup"]["assertions"])
    assert state["cleanup"] == "Completed"


@pytest.mark.parametrize("fail", [False, True])
def test_one_verifier_review_preserves_actual_evidence_and_controls_failure(tmp_path, fail):
    from wizard_kernel.ports.model import ModelFailure
    class ReviewedPolicy(RuntimePolicy):
        requires_verifier = True
        reviews = 0
        def request(self, role, context, model, **kwargs):
            if role != "verifier":
                return super().request(role, context, model, **kwargs)
            self.reviews += 1
            assert context["evidence"] and context["results"]["check"]["status"] == "passed"
            if fail:
                raise ModelFailure("http", "Provider unavailable", status=422)
            return model.model_validate({"investigation_id": context["investigation_id"], "assessment": "overall_sufficient"})
    policy = ReviewedPolicy()
    inv, state = run_app(tmp_path, policy)
    assert policy.reviews == 1
    assert state["results"]["check"]["status"] == "passed"
    assert state["cleanup"] == "Completed"
    assert inv.state.value == ("incomplete" if fail else "completed"), state
    if fail:
        assert state["verifier_failure"]["status"] == 422
    else:
        assert state["verifier"]["assessment"] == "overall_sufficient"
    assert state["cleanup"] == "Completed"
    assert [e["tool"] for e in state["executions"]] == ["start_process", "http_request"]
    assert policy.contexts[1]["resource_state"]["reachable_endpoints"]
    endpoint = policy.contexts[1]["resource_state"]["reachable_endpoints"][0]
    with pytest.raises(OSError):
        socket.create_connection((endpoint["host"], endpoint["port"]), timeout=0.5)
    assert state["results"]["check"]["assertions"][0]["actual"] == "200"
    assert "Actual application behavior" in fs_store.read_text(inv.id, "verification_report.md")


def test_real_browser_form_and_snapshot_through_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_TEST_DATA_JSON", json.dumps({"value": "authorized-test-value"}))
    inv, state = run_app(tmp_path, RuntimePolicy(browser=True))
    assert inv.state.value == "completed", state
    assert state["results"]["check"]["status"] == "passed"
    tools = [e["tool"] for e in state["executions"]]
    assert "browser_navigate" in tools and "browser_snapshot" in tools
    assert "browser_fill_form" in tools and "browser_click" in tools
    assert state["cleanup"] == "Completed"
    files = fs_store.inv_dir(inv.id).glob("observations/*.json")
    assert all("authorized-test-value" not in p.read_text(encoding="utf-8") for p in files)


def test_model_failure_persists_a_report_and_executes_nothing(tmp_path):
    from wizard_kernel.ports.model import ModelFailure
    class FailingPolicy(RuntimePolicy):
        def request(self, role, context, model, **kwargs):
            if role == "explorer":
                raise ModelFailure("incomplete", "finish_reason=length")
            return super().request(role, context, model, **kwargs)
    inv, state = run_app(tmp_path, FailingPolicy())
    assert inv.state.value == "incomplete"
    assert not state["executions"]
    assert state["failure_kind"] == "incomplete"
    assert "finish_reason=length" in fs_store.read_text(inv.id, "verification_report.md")


def test_provider_requests_canonical_strict_schema_and_classifies_truncation(monkeypatch):
    import httpx
    from wizard_kernel.ports.model import ModelPolicy, ModelFailure
    from wizard_kernel.contracts.verification import decision_model
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://provider.test")
    captured = []
    model = decision_model(["read_file"])
    valid = _response(model, {"kind": "tool", "action": {"tool": "read_file", "parameters": {"path": "file.txt"}}, "reason": ""})
    def post(url, **kwargs):
        captured.append(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": valid.model_dump_json()}}]})
    monkeypatch.setattr(httpx, "post", post)
    assert ModelPolicy().request("explorer", {"original_request": "read a file"}, model).action.tool == "read_file"
    body = captured[0]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["stream"] is False
    def truncated(*args, **kwargs):
        return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": '{"tool":"start_process"'}}], "usage": {"completion_tokens": 1024}})
    monkeypatch.setattr(httpx, "post", truncated)
    with pytest.raises(ModelFailure, match="finish_reason=length"):
        ModelPolicy().request("explorer", {}, model)


def test_failed_navigation_invalidates_old_page_proof():
    check = CheckSpec(id="check", description="Page reachable", assertions=[{
        "source": "browser", "field": "snapshot", "operator": "contains", "expected": "Available"}])
    good = observation("browser_snapshot", {"snapshot": "Available"})
    bad = good.model_copy(update={"source_tool": "browser_navigate", "success": False,
                                  "payload": {"ok": False, "error": "Connection refused"}})
    assert checks.verdict(checks.evaluate(check, [good, bad])) == "unverified"


def test_execution_cannot_be_replayed_or_overwrite_report(tmp_path):
    policy = RuntimePolicy()
    inv, state = run_app(tmp_path, policy)
    before = fs_store.read_text(inv.id, "verification_report.md")
    verification.run(inv, InvestigationManager(), policy)
    assert fs_store.read(inv.id, "verification.json") == state
    assert fs_store.read_text(inv.id, "verification_report.md") == before


def test_api_duplicate_submission_does_not_dispatch_twice(tmp_path, monkeypatch):
    from wizard_kernel.api import routes_investigations as api
    calls = []
    class Thread:
        def __init__(self, target, args, **kwargs): calls.append((target, args))
        def start(self): pass
    monkeypatch.setattr(api.threading, "Thread", Thread)
    manager = InvestigationManager()
    request = InvestigationRequest(repository_path=str(tmp_path), intent="verify", question="Check behavior")
    first = api.create_investigation(request, manager, "same-submit")
    second = api.create_investigation(request, manager, "same-submit")
    assert first["investigation_id"] == second["investigation_id"]
    assert len(calls) == 1
    assert calls[0][0] is verification.run


def test_one_runtime_service_is_the_normal_cli_stack():
    from wizard.cli.tui.services import build_specs
    assert [spec.key for spec in build_specs()] == ["kernel"]


def test_cancel_cleans_up_before_publishing_terminal_state(tmp_path):
    write_app(tmp_path)
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", options={"allowed_domains": ["localhost"]}))
    class CancelPolicy(RuntimePolicy):
        def request(self, role, context, model, **kwargs):
            if role == "explorer" and context["resource_state"]["processes"]:
                assert manager.request_cancel(inv.id)
                return _response(model, {"kind": "blocked", "action": None, "reason": "Cancelled"})
            return super().request(role, context, model, **kwargs)
    verification.run(inv, manager, CancelPolicy())
    saved = fs_store.read(inv.id, "verification.json")
    assert inv.state.value == "cancelled"
    assert saved["cleanup"] == "Completed"
    assert [e["tool"] for e in saved["executions"]] == ["start_process"]
    assert "State: cancelled" in fs_store.read_text(inv.id, "verification_report.md")


def test_report_mode_reads_saved_results_without_model(tmp_path):
    manager = InvestigationManager()
    previous = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify"))
    fs_store.write_text(previous.id, "verification_report.md", "# Existing evidence report\n")
    current = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="report"))
    verification.run(current, manager)
    assert current.state.value == "completed"
    assert "Existing evidence report" in fs_store.read_text(current.id, "verification_report.md")
    assert fs_store.read(current.id, "verification.json")["model_calls"] == 0


def test_events_survive_reconnect_with_cursor(tmp_path):
    from wizard_kernel.session import events
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify"))
    bus = events.create(inv.id)
    bus.emit(events.InvestigationStarted, {})
    bus.emit(events.ReportGenerated, {"report_path": "saved"})
    events._BUSSES.pop(inv.id)
    assert [e.seq for e in events.get_recent_events(1, inv.id)] == [2]


def test_provider_429_defers_shared_gate_without_retry(tmp_path, monkeypatch):
    import httpx
    from wizard_kernel.ports.model import ModelPolicy, ModelFailure
    from wizard_kernel.contracts.verification import decision_model
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "https://api.cerebras.ai")
    monkeypatch.setenv("WIZARD_CEREBRAS_GATE_DB", str(tmp_path / "gate.sqlite3"))
    class Gate:
        deferred = None
        def acquire(self, **kwargs): pass
        def defer(self, wait): self.deferred = wait
    policy = ModelPolicy()
    policy.gate = Gate()
    calls = []
    def rate_limited(*args, **kwargs):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "20"}, json={"error": "rate limited"})
    monkeypatch.setattr(httpx, "post", rate_limited)
    with pytest.raises(ModelFailure) as failure:
        policy.request("explorer", {}, decision_model(["read_file"]))
    assert failure.value.status == 429
    assert len(calls) == 1 and policy.gate.deferred == 20


def test_readiness_invalidates_after_owned_process_exits(tmp_path):
    from wizard_kernel.control.tool_validator import ToolRequestValidator
    from wizard_kernel.contracts.agent import ToolRequest
    validator = ToolRequestValidator(str(tmp_path), ["localhost"], True)
    validator.record_execution("start_process", {"command": "python app.py"}, {"ok": True, "data": {"handle_id": "owned"}})
    validator.record_execution("check_port", {"port": 43127}, {"ok": True, "data": {"port": 43127, "active": True}, "meta": {"handle_id": "owned"}})
    validator.record_execution("read_process", {"handle_id": "owned"}, {"ok": True, "data": {"handle_id": "owned", "is_running": False}})
    assert not validator.validate(ToolRequest(tool="browser_navigate", parameters={"url": "http://localhost:43127/"}), 5).valid
    assert not validator.validate(ToolRequest(tool="read_process", parameters={"handle_id": "another-investigation"}), 5).valid


def test_explain_cannot_execute_a_model_proposed_runtime_check(tmp_path):
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="explain",
                         question="Explain the application"))
    policy = RuntimePolicy()
    verification.run(inv, manager, policy)
    state = fs_store.read(inv.id, "verification.json")
    assert state["executions"] == []
    assert state["results"]["check"]["status"] == "unverified"
    assert "Execution capability disabled" in state["results"]["check"]["reason"]
    assert policy.contexts == []


def test_planner_schema_failure_preserves_rule_without_provider_input(tmp_path, monkeypatch):
    import httpx
    from wizard_kernel.ports.model import ModelPolicy, ModelFailure
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://provider.test")
    response = {"checks": [{"id": "check", "description": "private-input-marker",
                            "assertions": [], "unresolved_reason": "",
                            "capabilities": [], "depends_on": []}]}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200,
        headers={"x-request-id": "request-test"}, json={"choices": [{"finish_reason": "stop",
        "message": {"content": json.dumps(response)}}]}))
    policy = ModelPolicy()
    with pytest.raises(ModelFailure) as failed:
        policy.request("planner", {}, VerificationSpec)
    assert failed.value.status == 200
    assert failed.value.request_id == "request-test"
    assert "Check requires explicit expectations" in str(failed.value)
    assert "private-input-marker" not in str(failed.value)
    assert policy.last_metadata["validation_errors"][0]["location"] == ["checks", 0]
    assert "input" not in policy.last_metadata["validation_errors"][0]

    class FailedPolicy:
        provider_requests = 1
        last_metadata = policy.last_metadata
        def request(self, *a, **k):
            raise failed.value
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify"))
    verification.run(inv, manager, FailedPolicy())
    saved = fs_store.read(inv.id, "verification.json")
    assert saved["executions"] == []
    assert saved["provider_metadata"]["validation_errors"]
    assert "Check requires explicit expectations" in fs_store.read_text(inv.id, "verification_report.md")


def test_provider_progress_reports_gate_http_and_validation(monkeypatch):
    import httpx
    from wizard_kernel.ports.model import ModelPolicy
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://provider.test")
    spec = VerificationSpec(checks=[CheckSpec(id="check", description="Discover contract",
                                            unresolved_reason="Needs repository discovery")])
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200,
        json={"choices": [{"finish_reason": "stop", "message": {"content": spec.model_dump_json()}}]}))
    class Gate:
        def acquire(self, cancel_check=None, on_wait=None):
            on_wait(12)
    policy = ModelPolicy()
    policy.gate = Gate()
    progress = []
    policy.request("planner", {}, VerificationSpec,
                   on_progress=lambda stage, details: progress.append((stage, details)))
    assert [stage for stage, _ in progress] == ["waiting", "request", "response", "validated"]
    assert progress[1][1]["timeout_seconds"] == 60
    assert "test-key" not in json.dumps(progress)


def test_cancel_during_planner_preserves_validated_result_without_execution(tmp_path):
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify"))
    class CancelPolicy(RuntimePolicy):
        def request(self, role, context, model, **kwargs):
            result = super().request(role, context, model, **kwargs)
            manager.request_cancel(inv.id)
            return result
    verification.run(inv, manager, CancelPolicy())
    assert fs_store.read(inv.id, "plan.json")["checks"]
    assert fs_store.read(inv.id, "verification.json")["executions"] == []
    assert inv.state.value == "cancelled"


def test_tui_narrates_provider_wait_and_completion():
    from wizard.cli.tui.session import _narrate
    text, _ = _narrate("provider.progress", {"agent": "planner", "stage": "waiting", "wait_seconds": 12})
    assert "shared provider capacity" in text
    text, _ = _narrate("provider.progress", {"agent": "planner", "stage": "request", "timeout_seconds": 60})
    assert "request sent" in text and "60" in text
    text, _ = _narrate("agent.completed", {"agent_type": "planner"})
    assert "decision completed" in text


def test_browser_route_must_be_explicit_or_observed(tmp_path):
    from wizard_kernel.contracts.agent import ToolRequest
    from wizard_kernel.control.tool_validator import ToolRequestValidator
    validator = ToolRequestValidator(str(tmp_path), ["localhost"], True, navigation_targets=[])
    validator.record_execution("check_port", {"host": "localhost", "port": 12345},
                               {"ok": True, "data": {"active": True, "port": 12345}})
    def navigate(url):
        return validator.validate(ToolRequest(tool="browser_navigate", parameters={"url": url},
                                             reasoning="", node_id="step"), 5)
    assert navigate("http://localhost:12345/").valid
    rejected = navigate("http://localhost:12345/invented")
    assert not rejected.valid and "UNDISCOVERED_BROWSER_TARGET" in rejected.reason
    validator.record_execution("browser_snapshot", {}, {"ok": True, "data": {
        "url": "http://localhost:12345/", "links": [{"href": "http://localhost:12345/actual-link"}]}})
    assert navigate("http://localhost:12345/actual-link").valid


def test_agent_browser_rejects_selector_not_in_observed_refs():
    from wizard_kernel.world.browser.runtime import BrowserRuntime
    browser = BrowserRuntime(allowed_domains=["localhost"])
    with pytest.raises(ValueError, match="STALE_BROWSER_REF"):
        browser.click("#invented")
    assert not browser.started


def test_declared_service_plan_requires_actual_readiness_not_exit_code():
    service = "python -u server.py"
    spec = VerificationSpec(checks=[CheckSpec(id="startup", description="Start service",
        capabilities=["process"], assertions=[{"source": "command", "field": "exit_code",
        "operator": "equals", "expected": "0", "target": service}])])
    adjustments = verification._admit_plan(spec, {"command_candidates": [
        {"command": service, "lifecycle": "long_running"}]})
    check = spec.checks[0]
    assert adjustments and {a.field for a in check.assertions} == {"is_running", "active"}
    started = observation("start_process", {"handle_id": "owned", "command": service, "is_running": True})
    started = started.model_copy(update={"goal_id": "startup"})
    assert checks.verdict(checks.evaluate(check, [started])) == "unverified"
    probed = observation("check_port", {"active": True, "port": 12345})
    probed = probed.model_copy(update={"goal_id": "startup"})
    probed.payload["meta"] = {"handle_id": "owned"}
    assert checks.verdict(checks.evaluate(check, [started, probed])) == "passed"


def test_unknown_lifecycle_and_build_exit_expectations_are_not_rewritten():
    for lifecycle in ("unknown", "one_shot"):
        spec = VerificationSpec(checks=[CheckSpec(id="build", description="Build succeeds",
            capabilities=["process"], assertions=[{"source": "command", "field": "exit_code",
            "operator": "equals", "expected": "0", "target": "build-command"}])])
        assert verification._admit_plan(spec, {"command_candidates": [
            {"command": "build-command", "lifecycle": lifecycle}]}) == []
        assert spec.checks[0].assertions[0].source == "command"


def test_unresolved_html_proposal_remains_unverified_until_discovery():
    spec = VerificationSpec(checks=[CheckSpec(id="form", description="Display form",
        capabilities=["browser"], unresolved_reason="Discover the actual page",
        assertions=[{"source": "browser", "field": "snapshot", "operator": "contains",
                     "expected": "<form", "after_submission": True}])])
    assert verification._admit_plan(spec, {})
    assert spec.checks[0].assertions == []
    assert checks.verdict(checks.evaluate(spec.checks[0], [])) == "unverified"


def test_service_dependency_to_real_browser_submission_completes(tmp_path, monkeypatch):
    write_app(tmp_path)
    entry = command(sys.executable, "-u", "app.py")
    monkeypatch.setenv("WIZARD_TEST_DATA_JSON", json.dumps({"value": "authorized-test-value"}))
    monkeypatch.setattr(verification, "_discover_runnable_commands", lambda _: [
        {"command": entry, "cwd": ".", "lifecycle": "long_running"}])
    class WorkflowPolicy(RuntimePolicy):
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                return _response(model, {"checks": [
                    {"id": "startup", "description": "Start the declared service", "capabilities": ["process"],
                     "assertions": [{"source": "command", "field": "exit_code", "operator": "equals",
                                     "expected": "0", "target": entry}]},
                    {"id": "check", "description": "Submit the form and observe Complete", "workflow": "form_submission", "capabilities": ["browser"],
                     "depends_on": ["startup"], "unresolved_reason": "Discover actual browser form",
                     "assertions": [{"source": "browser", "field": "snapshot", "operator": "contains",
                                     "expected": "<form"}]}]})
            check = context["current_check"]
            if check["id"] == "check" and not check["assertions"] and (context["resource_state"]["browser"] or {}).get("controls"):
                return _response(model, {"kind": "refine", "action": None, "reason": "Use the observed form and requested result",
                    "refinement": {"observation_ids": [o["id"] for o in context["recent_observations"] if o["tool"] == "browser_snapshot"],
                    "assertions": [{"source": "browser", "field": "snapshot", "operator": "contains",
                                    "expected": "Complete", "after_submission": True}]}})
            return super().request(role, context, model, **kwargs)
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify",
        question="Start the app, submit the form and observe Complete", options={"budget": 12, "allowed_domains": ["localhost"]}))
    policy = WorkflowPolicy(browser=True)
    verification.run(inv, manager, policy)
    saved = fs_store.read(inv.id, "verification.json")
    assert inv.state.value == "completed", saved
    assert saved["results"]["startup"]["status"] == "passed"
    assert saved["results"]["check"]["status"] == "passed"
    assert saved["plan_adjustments"]
    assert fs_store.read(inv.id, "proposed_plan.json")["checks"][0]["assertions"][0]["field"] == "exit_code"
    assert saved["cleanup"] == "Completed"
    assert any(e["tool"] == "browser_click" and e["success"] for e in saved["executions"])
    assert all("check_scope" in c for c in policy.contexts)


def test_repository_assertions_match_windows_executor_paths():
    check = CheckSpec(id="check", description="Declared file exists", assertions=[{
        "source": "repository", "field": "exists", "operator": "equals",
        "expected": "true", "target": "client/package.json"}])
    actual = observation("path_exists", {"path": "client\\package.json", "exists": True})
    assert checks.verdict(checks.evaluate(check, [actual])) == "passed"


def test_unresolved_checks_cannot_request_evaluation_and_empty_values_are_schema_constrained():
    from wizard_kernel.contracts.verification import Assertion, decision_model
    from wizard_kernel.ports.model import strict_schema
    model = decision_model(["read_file"], allow_evaluate=False)
    with pytest.raises(ValueError):
        _response(model, {"kind": "evaluate", "action": None, "reason": "Ready"})
    assert strict_schema(Assertion)["$defs"]["snapshot_predicate"]["properties"]["expected"]["minLength"] == 1


def test_command_defaults_preserve_explicit_request(tmp_path):
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", targets=["runtime"]))
    assert "actually start or execute" in verification._effective_request(inv)
    assert inv.question == ""
    inv.question = "Check this exact requested outcome"
    assert verification._effective_request(inv) == inv.question


def test_empty_sentence_verify_runtime_executes_instead_of_file_checks(tmp_path, monkeypatch):
    write_app(tmp_path)
    entry = command(sys.executable, "-u", "app.py")
    monkeypatch.setattr(verification, "_discover_runnable_commands", lambda _: [
        {"command": entry, "cwd": ".", "lifecycle": "long_running"}])
    class Policy(RuntimePolicy):
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                assert "actually start or execute" in context["original_request"]
                return _response(model, {"checks": [{"id": "static", "description": "File exists",
                    "assertions": [{"source": "repository", "field": "exists", "operator": "equals",
                                    "expected": "true", "target": "missing-file"}]}]})
            self.contexts.append(context)
            return _response(model, {"kind": "tool", "action": {"tool": "start_process",
                "parameters": {"command": entry}}, "reason": "Execute the discovered service"})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify",
        targets=["runtime"], options={"budget": 3, "allowed_domains": ["localhost"]}))
    policy = Policy()
    verification.run(inv, manager, policy)
    state = fs_store.read(inv.id, "verification.json")
    assert inv.state.value == "completed", state
    assert state["results"]["runtime_smoke"]["status"] == "passed"
    assert [e["tool"] for e in state["executions"]] == ["start_process"]
    assert state["cleanup"] == "Completed"
    assert len(policy.contexts) == 1
    assert "verify runtime" in fs_store.read_text(inv.id, "verification_report.md")


def test_unspecified_startup_goal_gets_explicit_runtime_readiness_contract():
    spec = VerificationSpec(checks=[CheckSpec(id="start", description="Start application",
        capabilities=["process"], unresolved_reason="Discover which command starts it")])
    verification._admit_plan(spec, {"command_candidates": [{"command": "declared-entry", "lifecycle": "long_running"}]}, runtime_scope=True)
    assert {a.field for a in spec.checks[0].assertions} == {"is_running", "active"}
    assert spec.checks[0].unresolved_reason == ""
    assert checks.verdict(checks.evaluate(spec.checks[0], [])) == "unverified"


def test_tree_excludes_dependencies_and_uses_portable_paths(tmp_path):
    from wizard_kernel.world.tools import ToolExecutor
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "entry.py").write_text("pass")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "irrelevant.js").write_text("ignored")
    result = ToolExecutor(None, str(tmp_path)).execute({"tool": "list_tree", "params": {}})
    assert result["data"]["tree"] == ["client/entry.py"]


def test_initial_guessed_browser_url_is_not_locked_but_explicit_target_is():
    def specification(url):
        return VerificationSpec(checks=[CheckSpec(id="page", description="Open application",
            assertions=[{"source": "browser", "field": "url", "operator": "equals", "expected": url}])])
    inferred = specification("http://localhost:3000")
    assert verification._admit_plan(inferred, {})
    assert inferred.checks[0].assertions == []
    assert "browser" in inferred.checks[0].capabilities
    assert inferred.checks[0].unresolved_reason
    supplied = specification("https://target.test/required")
    assert verification._admit_plan(supplied, {}, explicit_targets=["https://target.test/required"]) == []
    assert supplied.checks[0].assertions[0].expected == "https://target.test/required"


def test_real_run_guessed_port_refinement_boundary_replays_with_real_browser(tmp_path, monkeypatch):
    write_app(tmp_path)
    entry = command(sys.executable, "-u", "app.py")
    monkeypatch.setattr(verification, "_discover_runnable_commands", lambda _: [
        {"command": entry, "cwd": ".", "lifecycle": "long_running"}])
    class ReplayPolicy(RuntimePolicy):
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                return _response(model, {"checks": [
                    {"id": "startup", "description": "Start app", "capabilities": ["process"],
                     "assertions": [{"source": "process", "field": field, "operator": "equals", "expected": "true"}
                                    for field in ("is_running", "active")]},
                    {"id": "page", "description": "Open application", "capabilities": ["browser"], "depends_on": ["startup"],
                     "assertions": [{"source": "browser", "field": "url", "operator": "equals", "expected": "http://localhost:3000"}]}]})
            self.contexts.append(context)
            if context["current_check"]["id"] == "startup":
                return _response(model, {"kind": "tool", "action": {"tool": "start_process", "parameters": {"command": entry}}, "reason": "Start declared application"})
            endpoint = context["resource_state"]["reachable_endpoints"][0]
            target = f"http://{endpoint['host']}:{endpoint['port']}/"
            if not context["current_check"]["assertions"]:
                return _response(model, {"kind": "refine", "action": None, "reason": "Use real discovered endpoint",
                    "refinement": {"observation_ids": [endpoint["observation_id"]], "assertions": [
                        {"source": "browser", "field": "url", "operator": "equals", "expected": target}]}})
            return _response(model, {"kind": "tool", "action": {"tool": "browser_navigate", "parameters": {"url": target}}, "reason": "Navigate discovered URL"})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", targets=["runtime"],
        question="Start application and open its browser page", options={"budget": 5, "allowed_domains": ["localhost"]}))
    verification.run(inv, manager, ReplayPolicy())
    state = fs_store.read(inv.id, "verification.json")
    assert inv.state.value == "completed", state
    assert state["results"]["page"]["status"] == "passed"
    assert state["cleanup"] == "Completed"
    assert any(item["response"]["decision"]["kind"] == "refine" for item in state["decision_results"])
    assert all(item["response"]["decision"]["action"]["parameters"].get("url") != "http://localhost:3000"
               for item in state["decision_results"] if item["response"]["decision"]["action"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console ownership regression")
def test_runtime_children_do_not_attach_to_the_tui_console(tmp_path, monkeypatch):
    from wizard_kernel.world.sandbox.local import LocalProcessRuntime
    original = subprocess.Popen
    flags = []
    def captured(*args, **kwargs):
        if kwargs.get("shell"):
            flags.append(kwargs.get("creationflags", 0))
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", captured)
    runtime = LocalProcessRuntime()
    runtime.start(str(tmp_path))
    try:
        result = runtime.exec(command(sys.executable, "-c", "print('captured')"))
        assert result.exit_code == 0 and "captured" in result.stdout
        process = runtime.exec_background(command(sys.executable, "-c", "import time; time.sleep(30)"))
        assert process.is_running
        assert len(flags) == 2
        assert all(flag & subprocess.CREATE_NO_WINDOW for flag in flags)
    finally:
        runtime.stop()


def test_tactical_schema_enforces_mutually_exclusive_decision_variants():
    from wizard_kernel.contracts.verification import decision_model
    from wizard_kernel.ports.model import strict_schema
    model = decision_model(["browser_click"])
    schema = strict_schema(model)
    assert schema["type"] == "object" and "anyOf" not in schema
    assert schema["properties"]["decision"]["anyOf"]
    tool = schema["$defs"]["ToolDecision"]
    assert tool["properties"]["refinement"]["type"] == "null"
    assert "anyOf" not in tool["properties"]["action"]  # One tool: non-null reference.
    refine = schema["$defs"]["RefineDecision"]
    assert refine["properties"]["action"]["type"] == "null"
    invalid = {"kind": "tool", "action": {"tool": "browser_click", "parameters": {"selector": "@e1"}},
               "refinement": {"assertions": [{"source": "browser", "field": "title", "operator": "contains", "expected": "Page"}],
                              "observation_ids": ["obs_one"]}, "reason": "Mixed decision"}
    with pytest.raises(ValueError):
        _response(model, invalid)
    valid = _response(model, {**invalid, "refinement": None})
    assert valid.kind == "tool" and valid.action.tool == "browser_click"


def test_root_env_test_inputs_reach_runtime_without_entering_build_output(tmp_path, monkeypatch):
    from wizard.cli.tui.services import build_specs
    monkeypatch.delenv("CEREBRAS_KEY", raising=False)
    monkeypatch.delenv("WIZARD_TEST_DATA_JSON", raising=False)
    (tmp_path / ".env").write_text("CEREBRAS_KEY=test-key\nWIZARD_TEST_DATA_JSON='{\"email\":\"fixture-input\"}'\n", encoding="utf-8")
    spec = build_specs(root=tmp_path)[0]
    assert json.loads(spec.env["WIZARD_TEST_DATA_JSON"])["email"] == "fixture-input"
    assert "fixture-input" not in spec.label and "fixture-input" not in repr(spec.argv)


@pytest.mark.parametrize("create_record", [False, True])
def test_actual_registration_then_login_through_agent_browser(tmp_path, monkeypatch, create_record):
    # Test application, not sample-specific code. Native HTTP POSTs create/check
    # an account; page state changes only when its actual API response succeeds.
    page = r"""<a href='/enroll'>Create account</a>
<script>
const route=location.pathname;
if(route==='/enroll' || route==='/access'){
 document.body.innerHTML='<form>'+(route==='/enroll'?'<label>Name<input name="name" required></label>':'')+
 '<label>Email<input name="email" type="email" required></label><label>Password<input name="password" type="password" required></label>'+ 
 '<button type="submit">'+(route==='/enroll'?'Create account':'Log in')+'</button></form>';
 document.querySelector('form').onsubmit=async(e)=>{e.preventDefault();
  const data=Object.fromEntries(new FormData(e.target));
  const result=await fetch(route,{method:'POST',body:JSON.stringify(data)});
  if(result.ok)document.body.innerHTML=route==='/enroll'?'Account created <a href="/access">Continue to login</a>':'Authenticated <a href="/record">Add record</a>';
  else document.body.innerHTML='Authentication failed';
 };
}
if(route==='/record'){
 document.body.innerHTML='<form><label>Text<input name="text" required></label><label>Description<input name="description"></label><label>Due optional<input type="date"></label><button type="submit">Save</button></form>';
 document.querySelector('form').onsubmit=(e)=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));document.body.replaceChildren();const row=document.createElement('div');row.textContent='Record saved: '+data.text;document.body.append(row);};
}
</script>"""
    app = "from http.server import BaseHTTPRequestHandler,HTTPServer\nimport json\naccounts={}\npage=" + repr(page) + "\n" + """class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(page.encode())
 def do_POST(self):
  data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  email,password=data.get('email'),data.get('password')
  if self.path=='/enroll':
   ok=bool(email and password and data.get('name') and email not in accounts)
   if ok: accounts[email]=password
  else: ok=accounts.get(email)==password
  self.send_response(200 if ok else 400);self.end_headers();self.wfile.write(b'{}')
server=HTTPServer(('127.0.0.1',0),Handler)
print(f'http://localhost:{server.server_port}',flush=True)
server.serve_forever()
"""
    (tmp_path / "app.py").write_text(app, encoding="utf-8")
    inputs = {}
    generate = verification._local_test_inputs
    def capture_inputs(inv):
        result = generate(inv)
        inputs.update(result)
        return result
    monkeypatch.delenv("WIZARD_TEST_DATA_JSON", raising=False)
    monkeypatch.setenv("WIZARD_ALLOW_DISPOSABLE_LOCAL_ACCOUNTS", "true")
    monkeypatch.setattr(verification, "_local_test_inputs", capture_inputs)
    class AuthPolicy(RuntimePolicy):
        attempted_empty_submit = False

        def request(self, role, context, model, **kwargs):
            if role == "planner":
                checks_spec = [
                    {"id": "login", "description": "Log in with the created account and observe Authenticated",
                     "workflow": "login", "capabilities": ["browser"], "unresolved_reason": "Discover actual login controls"},
                    {"id": "registration", "description": "Create account and observe Account created",
                     "workflow": "registration", "capabilities": ["browser"], "unresolved_reason": "Discover actual registration controls"}]
                if create_record:
                    checks_spec.append({"id": "record", "description": "Create and observe a record", "workflow": "form_submission",
                                        "capabilities": ["browser"], "depends_on": ["login"], "unresolved_reason": "Discover record creation controls"})
                return model.model_validate({"checks": checks_spec})
            state = context["resource_state"]
            page_state = state["browser"] or {}
            if not state["processes"]:
                action = {"tool": "start_process", "parameters": {"command": command(sys.executable, "-u", "app.py")}}
            elif not state["browser"]:
                assert context["discovery_required"]
                assert "Unknown page routes" in context["discovery_instruction"]
                assert "BlockedDecision" not in model.model_json_schema().get("$defs", {})
                endpoint = state["reachable_endpoints"][0]
                action = {"tool": "browser_navigate", "parameters": {"url": f"http://{endpoint['host']}:{endpoint['port']}/"}}
            elif page_state.get("snapshot_required"):
                action = {"tool": "browser_snapshot", "parameters": {}}
            elif not context["current_check"]["assertions"]:
                snapshot_ids = [o["id"] for o in context["recent_observations"] if o["tool"] == "browser_snapshot"]
                if not snapshot_ids:
                    action = {"tool": "browser_snapshot", "parameters": {}}
                else:
                    expected = context["public_test_inputs"]["text"] if context["current_check"]["id"] == "record" else (
                        "Account created" if context["current_check"]["workflow"] == "registration" else "Authenticated")
                    return _response(model, {"kind": "refine", "action": None, "reason": "Observe the requested distinct submission result",
                        "refinement": {"observation_ids": snapshot_ids,
                        "assertions": [{"source": "browser", "field": "text" if context["current_check"]["id"] == "record" else "snapshot", "operator": "contains", "expected": expected, "after_submission": True}]}})
            else:
                controls = page_state.get("controls", [])
                link = next((c for c in controls if c["role"] == "link"), None)
                if link:
                    action = {"tool": "browser_click", "parameters": {"selector": link["selector"]}}
                elif context["current_check"]["workflow"] == "registration" and not self.attempted_empty_submit:
                    self.attempted_empty_submit = True
                    assert any(c.get("filled") is False for c in controls)
                    submit = next(c for c in controls if c.get("submits_form"))
                    action = {"tool": "browser_click", "parameters": {"selector": submit["selector"]}}
                elif context["recent_observations"] and any(o["tool"] == "browser_fill_form" for o in context["recent_observations"]):
                    submit = next(c for c in controls if c.get("submits_form"))
                    action = {"tool": "browser_click", "parameters": {"selector": submit["selector"]}}
                else:
                    fields = [{"selector": c["selector"], "value_ref": c["name"].lower()}
                              for c in controls if c["role"] == "textbox"]
                    action = {"tool": "browser_fill_form", "parameters": {"fields": fields}}
            return _response(model, {"kind": "tool", "action": action, "reason": "Use current observed page controls"})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent="verify", targets=["runtime"],
        question="Register an account, log in, and observe Authenticated" + (" and create a record" if create_record else ""),
        options={"budget": 20 if create_record else 14, "allowed_domains": ["localhost"]}))
    verification.run(inv, manager, AuthPolicy(browser=True))
    state = fs_store.read(inv.id, "verification.json")
    assert inv.state.value == "completed", state
    assert state["results"]["registration"]["status"] == "passed"
    rejections = [o for o in fs_store.read(inv.id, "events.json") if o["event_type"] == "tool.rejected"]
    assert any("FORM_NOT_FILLED" in o["payload"].get("reason", "") for o in rejections)
    assert state["results"]["login"]["status"] == "passed"
    assert state["checks"][0]["depends_on"] == ["registration"]
    assert all(c["assertions"][0]["after_submission"] for c in state["checks"])
    assert sum(e["tool"] == "browser_fill_form" and e.get("success") for e in state["executions"]) == (3 if create_record else 2)
    if create_record:
        assert state["results"]["record"]["status"] == "passed"
        assert sum(e["check_id"] == "record" and e["tool"] == "browser_click" and e.get("success") for e in state["executions"]) == 2
    requested_fills = [d["response"]["decision"]["action"] for d in state["decision_results"]
                       if (d["response"]["decision"].get("action") or {}).get("tool") == "browser_fill_form"]
    assert all("value_ref" in field and "text" not in field
               for action in requested_fills for field in action["parameters"]["fields"])
    assert state["cleanup"] == "Completed"
    stored = "".join(p.read_text() for p in fs_store.inv_dir(inv.id).glob("observations/*.json"))
    assert "Account created" in stored and "Authenticated" in stored
    assert state["test_input_source"] == "disposable_local" and inputs
    assert all(value not in stored for key, value in inputs.items() if key not in {"text", "description"})
    if create_record:
        assert inputs["text"] in stored


def test_disposable_inputs_are_unique_local_only_and_opt_in(tmp_path, monkeypatch):
    manager = InvestigationManager()
    def request(domains, intent="verify"):
        return manager.create(InvestigationRequest(repository_path=str(tmp_path), intent=intent,
            options={"allowed_domains": domains}))
    monkeypatch.delenv("WIZARD_ALLOW_DISPOSABLE_LOCAL_ACCOUNTS", raising=False)
    assert verification._local_test_inputs(request(["localhost"])) == {}
    monkeypatch.setenv("WIZARD_ALLOW_DISPOSABLE_LOCAL_ACCOUNTS", "true")
    one = verification._local_test_inputs(request(["localhost", "127.0.0.1"]))
    two = verification._local_test_inputs(request(["localhost"]))
    assert one["email"] != two["email"] and one["password"] != two["password"]
    assert one["password_confirmation"] == one["password"]
    assert one["email"].endswith("@example.invalid")
    assert verification._local_test_inputs(request(["external.test"])) == {}
    assert verification._local_test_inputs(request(["localhost", "external.test"])) == {}
    assert verification._local_test_inputs(request(["localhost"], "explain")) == {}


def test_assertion_schema_encodes_source_field_and_expected_types():
    from wizard_kernel.contracts.verification import Assertion
    from wizard_kernel.ports.model import strict_schema
    schema = strict_schema(Assertion)
    body = schema["$defs"]["content_predicate"]["properties"]
    assert body["source"]["const"] == "repository"
    numeric = schema["$defs"]["status_code_predicate"]["properties"]
    assert numeric["expected"]["type"] == "integer"
    assert numeric["expected"]["minimum"] == 100 and numeric["expected"]["maximum"] == 599
    assert numeric["operator"]["const"] == "equals"
    with pytest.raises(ValueError):
        Assertion(source="browser", field="content", operator="contains", expected="Text")
    with pytest.raises(ValueError):
        Assertion(source="process", field="active", operator="equals", expected="ready")


def test_native_form_references_only_allow_authorized_values():
    from wizard_kernel.contracts.verification import decision_model
    model = decision_model(["browser_type"], value_refs=["email", "password"])
    with pytest.raises(ValueError):
        _response(model, {"kind": "tool", "action": {"tool": "browser_type", "parameters": {
            "selector": "@e1", "value_ref": "invented_password"}}, "reason": "Wrong ref"})
    result = _response(model, {"kind": "tool", "action": {"tool": "browser_type", "parameters": {
        "selector": "@e1", "value_ref": "password"}}, "reason": "Authorized ref"})
    assert result.action.parameters.value_ref == "password"


def test_refinement_diagnostics_identify_selected_branch_without_values(monkeypatch):
    import httpx
    from wizard_kernel.ports.model import ModelPolicy, ModelFailure
    from wizard_kernel.contracts.verification import decision_model
    monkeypatch.setenv("CEREBRAS_KEY", "test-key")
    monkeypatch.setenv("WIZARD_LLM_BASE_URL", "http://provider.test")
    invalid = {"decision": {"kind": "refine", "action": None, "reason": "Refine",
        "refinement": {"observation_ids": ["obs_one"], "assertions": [{
            "source": "browser", "field": "content", "operator": "contains", "expected": "private-expected-marker"}]}}}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(invalid)}}]}))
    policy = ModelPolicy()
    with pytest.raises(ModelFailure):
        policy.request("explorer", {}, decision_model(["browser_snapshot"]))
    errors = json.dumps(policy.last_metadata["validation_errors"])
    assert "ToolDecision" not in errors and "refine" in errors and "source" in errors
    assert policy.last_metadata["response_shape"]["kind"] == "refine"
    assert "private-expected-marker" not in json.dumps(policy.last_metadata)


def test_new_account_ordering_and_login_requires_its_own_submission():
    spec = VerificationSpec(checks=[
        CheckSpec(id="login", description="Log in", workflow="login", capabilities=["browser"],
                  unresolved_reason="Discover actual login result"),
        CheckSpec(id="register", description="Create account", workflow="registration", capabilities=["browser"],
                  unresolved_reason="Discover actual creation result", depends_on=["login"])])
    assert verification._account_dependencies(spec, True)
    assert spec.checks[0].depends_on == ["register"] and spec.checks[1].depends_on == []
    login = CheckSpec(id="login", description="Login succeeds", workflow="login", assertions=[{
        "source": "browser", "field": "snapshot", "operator": "contains",
        "expected": "Authenticated", "after_submission": True}])
    registered = observation("browser_click", {"submitted_form": True, "page_observation": {"snapshot": "Authenticated"}})
    registered = registered.model_copy(update={"goal_id": "register"})
    current = observation("browser_snapshot", {"snapshot": "Authenticated"})
    current = current.model_copy(update={"goal_id": "login"})
    assert checks.verdict(checks.evaluate(login, [registered, current])) == "unverified"


def test_static_form_text_cannot_be_refined_into_auth_success(tmp_path):
    class BadAuthCriteria(RuntimePolicy):
        snapshot_id = None
        def request(self, role, context, model, **kwargs):
            if role == "planner":
                return model.model_validate({"checks": [{"id": "check", "description": "Create account",
                    "workflow": "registration", "capabilities": ["browser"], "unresolved_reason": "Discover registration result"}]})
            if (context["resource_state"]["browser"] or {}).get("controls"):
                if self.snapshot_id is None:
                    self.snapshot_id = next(o["id"] for o in context["recent_observations"] if o["tool"] == "browser_snapshot")
                return _response(model, {"kind": "refine", "action": None, "reason": "Incorrectly use static form label",
                    "refinement": {"observation_ids": [self.snapshot_id], "assertions": [{
                        "source": "browser", "field": "snapshot", "operator": "contains", "expected": "Input"}]}})
            return super().request(role, context, model, **kwargs)
    inv, saved = run_app(tmp_path, BadAuthCriteria(browser=True))
    assert inv.state.value == "incomplete", saved
    assert saved["results"]["check"]["status"] == "unverified"
    assert "identical invalid auth criteria" in saved["stop_reason"]
    assert not any(e["tool"] in {"browser_click", "browser_fill_form"} for e in saved["executions"])
    assert saved["cleanup"] == "Completed"
