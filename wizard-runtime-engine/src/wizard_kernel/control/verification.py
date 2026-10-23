"""Runtime v2: one owner, explicit checks, one tactical loop, real executors."""
from __future__ import annotations

import hashlib
import copy
import re
import json
import time
import uuid
import threading
from urllib.parse import urlsplit
from dataclasses import replace
from pathlib import Path

from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
from wizard_kernel.contracts.status import LifecycleState, is_terminal
from wizard_kernel.contracts.verification import TOOL_ACTIONS, VerificationSpec, decision_model, planning_model
from wizard_kernel.control import checks, flow_trace
from wizard_kernel.world import scanner
from wizard_kernel.control.loop import _probe_started_process, _TOOL_TO_OBS_TYPE, _emit_browser_narration, _current_page, _emit_tool_observed
from wizard_kernel.control.tool_validator import ToolRequestValidator
from wizard_kernel.context.packager import _discover_runnable_commands
from wizard_kernel.ports.model import ModelPolicy, prepare_context
from wizard_kernel.reality.observations import ObservationStore
from wizard_kernel.session import events
from wizard_kernel.storage import fs_store
from wizard_kernel.world.sandbox import get_sandbox
from wizard_kernel.world.tools import ToolExecutor
from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.belief.evidence import EvidenceEngine
from wizard_kernel.belief import extractors, trust
from wizard_kernel.control.investigation_graph import InvestigationGraph, register_graph


def _process_output_sink(bus, execution_id, goal_id, sanitize, secret_window=0):
    """Stream real pipe deltas; final tool observations remain the proof boundary."""
    pending = {}
    lock = threading.Lock()

    def output(packet):
        key = (packet["handle_id"], packet["stream"])
        with lock:
            text = sanitize(pending.get(key, "") + packet["text"])
            count = len(text) if packet.get("eof") else max(0, len(text) - secret_window)
            pending[key] = text[count:]
            delta = text[:count]
            if delta:
                bus.emit("process.output", {"execution_id": execution_id, "goal_id": goal_id,
                    "handle_id": packet["handle_id"], "pid": packet["pid"],
                    "stream": packet["stream"], "text": delta})
    return output


def _redact(value, authorized, public_refs=()):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if flow_trace.safe_text("", key=str(k)) == "[REDACTED]" else _redact(v, authorized, public_refs)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, authorized, public_refs) for v in value]
    if isinstance(value, str):
        for reference, secret in authorized.items():
            if secret and reference not in public_refs:
                value = value.replace(secret, "[REDACTED]")
        value = flow_trace.safe_text(value, limit=len(value) + 1)
    return value


def _resources(observations):
    processes, endpoints, page, form = {}, {}, None, None
    for obs in observations:
        data = obs.payload.get("data") or {}
        if obs.source_tool in {"start_process", "read_process"}:
            handle = data.get("handle_id") or (obs.payload.get("meta") or {}).get("handle_id")
            if handle:
                processes[handle] = {k: data.get(k) for k in ("handle_id", "pid", "command", "cwd", "is_running", "exit_code")}
                processes[handle]["observation_id"] = obs.id
                processes[handle]["output"] = str(data.get("stdout_so_far") or data.get("stderr_so_far") or "")[-1500:]
                if data.get("is_running") is False:
                    endpoints = {k: v for k, v in endpoints.items() if v.get("handle_id") != handle}
        if obs.source_tool == "kill_process":
            handle = data.get("killed")
            if handle in processes:
                processes[handle]["is_running"] = False
                endpoints = {k: v for k, v in endpoints.items() if v.get("handle_id") != handle}
        if obs.source_tool == "check_port":
            key = (str(data.get("host") or "localhost"), data.get("port"))
            if data.get("active"):
                endpoints[key] = {"host": key[0], "port": key[1], "observation_id": obs.id,
                                  "handle_id": (obs.payload.get("meta") or {}).get("handle_id")}
            else:
                endpoints.pop(key, None)
        if obs.source_tool in {"browser_navigate", "http_request"} and not obs.success:
            target = (obs.payload.get("meta") or {}).get("target_url")
            if target:
                parsed = urlsplit(target)
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                endpoints = {k: v for k, v in endpoints.items() if not (v["port"] == port and
                             ToolRequestValidator._endpoint_host(v["host"]) == ToolRequestValidator._endpoint_host(parsed.hostname or ""))}
        if obs.source_tool.startswith("browser_"):
            if obs.source_tool in {"browser_navigate", "browser_back", "browser_click", "browser_type"}:
                form = None
            elif obs.source_tool == "browser_fill_form":
                form = {"observation_id": obs.id, "all_filled": bool(obs.success and data.get("all_filled")),
                        "fields": [{"selector": f.get("selector"), "typed": f.get("typed")} for f in data.get("fields", [])]}
            if obs.source_tool in {"browser_navigate", "browser_back"} and not obs.success:
                page = None
            elif obs.success:
                observed = data.get("page_observation") or data
                if "snapshot" in observed or "controls" in observed:
                    page = {k: v for k, v in observed.items() if k in {"url", "title", "snapshot", "text", "controls", "links", "controls_complete", "text_truncated", "snapshot_truncated"}}
                    page["observation_id"] = obs.id
                elif obs.source_tool in {"browser_navigate", "browser_back"}:
                    page = {"url": observed.get("url"), "snapshot_required": True}
    return {"processes": list(processes.values()), "reachable_endpoints": list(endpoints.values()), "browser": page,
            "form_state": form}


def _state_identity(value):
    """Evidence references change on repeated reads; resource facts may not."""
    def facts(item):
        if isinstance(item, dict):
            return {k: facts(v) for k, v in item.items() if k not in {"observation_id", "created_at"}}
        if isinstance(item, list):
            return [facts(v) for v in item]
        return item
    return hashlib.sha256(json.dumps(facts(value), sort_keys=True, default=str).encode()).hexdigest()


def _form_submission_rejection(check, page, selector):
    controls = page.get("controls", [])
    if not any(c.get("selector") == selector and c.get("submits_form") for c in controls):
        return None
    missing = [c.get("name") or c.get("selector") for c in controls
               if c.get("filled") is False and (c.get("required") or check.workflow in {"registration", "login"})]
    if missing:
        return "FORM_NOT_FILLED: fill the observed fields before submitting: " + ", ".join(missing)
    return None


def _local_test_inputs(inv):
    """Authorized disposable input capability, confined to local verification.

    Values are generated once per investigation; names only enter agent context.
    They do not prove signup/login succeeds and never enable external signup.
    """
    import os
    import secrets
    from urllib.parse import urlsplit
    enabled = os.environ.get("WIZARD_ALLOW_DISPOSABLE_LOCAL_ACCOUNTS", "").lower() in {"1", "true", "yes"}
    domains = inv.options.get("allowed_domains") or []
    if not enabled or inv.intent != "verify" or not domains:
        return {}
    if any(ToolRequestValidator._endpoint_host(domain) != "loopback" for domain in domains):
        return {}
    if any(urlsplit(t).scheme in {"http", "https"} and
           ToolRequestValidator._endpoint_host(urlsplit(t).hostname or "") != "loopback" for t in inv.targets):
        return {}
    identity = uuid.uuid4().hex
    password = secrets.token_urlsafe(24)
    return {"name": "Wizard test " + identity[:10], "email": "wizard-test-" + identity + "@example.invalid",
            "text": "Wizard verification " + identity[:12], "description": "Disposable local verification record " + identity[:12],
            "password": password, "password_confirmation": password}


def _effective_request(inv):
    """Command and target define the request when no sentence was supplied."""
    if inv.question.strip():
        return inv.question
    scopes = ", ".join(inv.targets) or "the repository"
    if inv.intent == "verify" and "runtime" in inv.targets:
        return ("Verify runtime behavior: discover the application's declared startup command, "
                "actually start or execute it, and measure its result. For a long-running service, "
                "verify running state and an actual listener/reachability probe. For a terminating "
                "command, verify its exit status and output. Repository inspection is preparation, "
                "not the requested outcome. Do not make file existence checks prerequisites. "
                "Report execution evidence and concrete blockers; do not invent authentication workflows.")
    if inv.intent == "verify":
        return f"Verify {scopes} using appropriate measurable checks and actual evidence; report unsupported checks honestly."
    if inv.intent == "investigate":
        return f"Investigate {scopes}: inspect relevant implementation and report evidence-backed findings and limitations."
    if inv.intent == "explain":
        return f"Explain {scopes} from relevant repository implementation; do not start the application."
    return f"Show the saved report for {scopes}; do not perform another investigation."


def _context(inv, check, results, observations, available, discovery, authorized, public_refs=(), *, preferred_ids=()):
    from wizard_kernel.ports.prompts import BROWSER_COMMANDS
    recent = []
    for obs in observations[-3:]:
        data = obs.payload.get("data") or {}
        if obs.source_tool.startswith("browser_"):
            data = {k: v for k, v in data.items() if k in {"url", "clicked", "typed", "all_filled", "submitted_form", "fields"}}
        elif obs.source_tool in {"start_process", "read_process"}:
            data = {k: v for k, v in data.items() if k in {"handle_id", "is_running", "exit_code"}}
        elif obs.source_tool == 'read_file':
            data = {k: v for k, v in data.items() if k != 'content'}
        recent.append({"id": obs.id, "tool": obs.source_tool, "success": obs.success,
                       "result": flow_trace.safe_text(json.dumps(data or obs.payload, default=str), limit=2000)})
    resource_state = _resources(observations)
    page = resource_state.get("browser")
    if page:
        page["links"] = page.get("links", [])[:20]
        snapshot = str(page.get("snapshot") or "")
        page["snapshot"] = snapshot if len(snapshot) <= 3500 else snapshot[:2200] + "\n[bounded: middle omitted]\n" + snapshot[-1300:]
        page["text"] = str(page.get("text") or "")[:2000]
        page["controls"] = [{k: v for k, v in c.items() if k != "value"} for c in page.get("controls", [])[:30]]
    auth_progress = None
    if check.workflow in {"registration", "login", "form_submission"}:
        scoped = [o for o in observations if o.goal_id == check.id]
        submission = next((o for o in reversed(scoped) if o.success and o.source_tool == "browser_click"
                           and (o.payload.get("data") or {}).get("submitted_form")), None)
        auth_progress = {"workflow": check.workflow, "submitted": bool(submission),
                         "submission_observation_id": submission.id if submission else None,
                         "next_objective": "Discover and submit the requested form using observed controls"}
        if submission:
            before = scoped[:scoped.index(submission)]
            before_page = _resources(before).get("browser") or {}
            last_mutation = max(i for i, o in enumerate(scoped) if o is submission or
                                o.source_tool in {"browser_navigate", "browser_back", "browser_click", "browser_type", "browser_fill_form"})
            result_observations = [o.id for o in scoped[last_mutation + 1:]
                                   if o.success and o.source_tool in {"browser_snapshot", "browser_extract"}
                                   and ((o.payload.get("data") or {}).get("snapshot")
                                        or ((o.payload.get("data") or {}).get("page_observation") or {}).get("snapshot"))]
            auth_progress.update(
                result_observation_ids=result_observations[-2:],
                pre_submission_page={"url": before_page.get("url"), "snapshot": str(before_page.get("snapshot") or "")[:1500]},
                next_objective="Submission already executed. Inspect the resulting page for evidence of the requested outcome. If success criteria are unresolved, refine browser post-submission criteria from actual observations; do not rediscover or resubmit the completed form. A redirect alone is not proof of authentication.")
        auth_progress["recent_rejections"] = [
            flow_trace.safe_text(o.payload.get("reason") or o.payload.get("error") or "", limit=700)
            for o in scoped if o.obs_type == "agent_failure"][-2:]
    packet = {"original_request": flow_trace.safe_text(_redact(_effective_request(inv), authorized), limit=8000), "command_family": inv.intent,
            "targets": [flow_trace.safe_text(t, limit=1600) for t in inv.targets],
            "current_check": check.model_dump(), "assertion_results": [
                {**r, 'actual': flow_trace.safe_text(str(r['actual']), limit=400) if r.get('actual') is not None else None}
                for r in results],
            "check_scope": "Complete this check only; dependent UI checks run after its readiness requirements pass",
            "refinement_policy": "For authentication, process readiness is preparation, not an authentication result. Navigate and inspect the actual page first; refine only browser post-submission result criteria using this check's browser observations.",
            "discovery_required": bool(not check.assertions and not resource_state["browser"] and "browser_navigate" in available),
            "discovery_instruction": "Unknown page routes, fields and result criteria are discovery work, not a blocker. A backend API listener or error page is not the requested UI. If controls are absent, inspect startup contracts and start missing application components with start_process; then probe their actual endpoints. Do not guess routes. TCP reachability does not prove UI readiness or authentication success.",
            "workflow": [{"id": g.get("id"), "description": g.get("name"), "status": g.get("state")}
                         for g in inv.active_goals[:8]],
            "resource_state": resource_state, "recent_observations": recent,
            "authentication_progress": auth_progress,
            "form_instruction": "Before submitting, use browser_fill_form with authorized value_refs for the observed empty fields (filled=false). Never click an authentication submit control before filling its fields. filled flags report actual DOM state without disclosing values. Do not refill unchanged successful fields.",
            "available_tools": available,
            "browser_tool_usage": {name: BROWSER_COMMANDS[name] for name in available if name in BROWSER_COMMANDS},
            "discovery": {"key_files": discovery.get("key_files", [])[:12],
                          "extensions": discovery.get("extensions", {}),
                          "command_candidates": discovery.get("command_candidates", [])[:8],
                          "documents": [{"path": d["path"], "observation_id": d["observation_id"],
                                         "excerpt": str(d.get("content") or "")[:600]}
                                        for d in discovery.get("documents", [])[:3]]},
            "authorized_value_refs": list(authorized),
            "public_test_inputs": {key: authorized[key] for key in public_refs},
            "test_input_usage": "Reuse authorized identity refs for signup/login. For requested local data-entry operations, use authorized text/description refs for discovered text fields. Never substitute email/password refs for ordinary record contents. Values are not proof; observe the actual submission and resulting record.",
            "remaining_tool_budget": inv.budget_remaining}
    packet['repository_evidence'] = [
        {'observation_id': o.id, 'path': (o.payload.get('data') or {}).get('path'),
         'success': o.success, 'bytes_read': (o.payload.get('data') or {}).get('bytes_read'),
         'excerpt': flow_trace.safe_text(str((o.payload.get('data') or {}).get('content') or ''), limit=1200)}
        for o in observations if o.source_tool == 'read_file']
    content_budget = 12000
    contents = list(zip(packet['repository_evidence'], [o for o in observations if o.source_tool == 'read_file']))
    contents.reverse()
    contents.sort(key=lambda pair: pair[1].id not in preferred_ids)
    for item, obs in contents:
        content = str((obs.payload.get('data') or {}).get('content') or '')
        limit = min(8000, content_budget)
        item['excerpt'] = flow_trace.safe_text(content, limit=limit) if limit else ''
        item['content_complete'] = len(content) <= limit
        content_budget -= min(len(content), limit)
    packet['repository_results'] = [
        {'observation_id': o.id, 'tool': o.source_tool, 'success': o.success,
         'result': _redact(o.payload.get('data') or {}, authorized, public_refs)}
        for o in observations if o.source_tool in {'list_tree', 'search_files', 'path_exists'}][-8:]
    packet['refinement_feedback'] = [o.payload for o in observations
        if o.goal_id == check.id and o.obs_type == 'agent_failure' and o.payload.get('details')][-3:]
    packet['evidence_instruction'] = 'Repository evidence is shared across checks. Reuse listed observation IDs; identical reads return cached evidence, not new information. Choose a different relevant file or evaluate satisfied predicates.'
    if available and set(available) <= {'read_file', 'search_files', 'list_tree', 'path_exists'}:
        for key in ('refinement_policy', 'discovery_required', 'discovery_instruction', 'authentication_progress',
                    'form_instruction', 'browser_tool_usage', 'authorized_value_refs', 'public_test_inputs', 'test_input_usage'):
            packet.pop(key, None)
    if page:
        # Once a page is observed, its structure drives tactics. Repository
        # contracts remain accessible through read_file without retransmission.
        packet["discovery"]["documents"] = [{"path": d["path"], "observation_id": d["observation_id"]}
                                               for d in discovery.get("documents", [])[:8]]
    sources = {o.id: o for o in observations}
    ordered_evidence = sorted(packet['repository_evidence'], key=lambda item: item['observation_id'] not in preferred_ids)
    packet['repository_evidence'] = ordered_evidence[:16] if preferred_ids else ordered_evidence[-16:]
    for item in packet['repository_evidence']:
        data = sources[item['observation_id']].payload.get('data') or {}
        item['content_complete'] = not bool(data.get('truncated')) and len(item['excerpt']) >= len(str(data.get('content') or ''))
    packet['repository_requests'] = [{'observation_id': o.id, 'tool': o.source_tool,
        'parameters': (o.payload.get('meta') or {})} for o in observations
        if o.source_tool in {'read_file', 'list_tree', 'search_files', 'path_exists'}][-16:]
    packet['repository_read_history'] = [{'observation_id': o.id, 'goal_id': o.goal_id,
        'path': (o.payload.get('data') or {}).get('path'), 'success': o.success}
        for o in observations if o.source_tool == 'read_file'][-24:]
    if page and not (set(check.capabilities) == {'repository'}):
        # Match the working browser path: the current page drives tactics.
        # Repository contents remain available via read_file, not retransmitted
        # as a second discovery transcript on every browser decision.
        for key in ('repository_evidence', 'repository_results', 'repository_requests', 'repository_read_history'):
            packet.pop(key, None)
        # Keep current controls/body evidence; do not repeat the whole startup
        # log and the same controls a second time in a long ARIA excerpt.
        for process in resource_state['processes']:
            process['output'] = str(process.get('output') or '')[-300:]
        if page.get('controls_complete') and len(page.get('snapshot', '')) > 1500:
            page['snapshot'] = page['snapshot'][:1500]
            page['snapshot_excerpt'] = True
    return packet



def supporting_repository_sources(assertion, observations):
    """Locate existing positive proof for feedback; never retarget accepted criteria."""
    from wizard_kernel.contracts.verification import Assertion, CheckSpec
    if assertion.source != 'repository' or assertion.field != 'content' or assertion.operator not in {'contains', 'equals'}:
        return []
    matches = []
    for obs in observations:
        if not obs.success or obs.source_tool != 'read_file':
            continue
        predicate = Assertion.model_validate({**assertion.model_dump(), 'target': obs.id})
        preview = CheckSpec(id='evidence_lookup', description='Locate existing proof', assertions=[predicate])
        if checks.verdict(checks.evaluate(preview, [obs])) == 'passed':
            matches.append({'observation_id': obs.id, 'path': (obs.payload.get('data') or {}).get('path')})
    return matches


def refinement_errors(check, refinement, observations, eligible_ids, *, require_content=False):
    """Explain rejected references without changing accepted requirements or evidence."""
    errors = {}
    if check.assertions:
        errors['grounded_requirements'] = [a.model_dump() for a in check.assertions]
    invalid = sorted(set(refinement.observation_ids) - set(eligible_ids))
    if invalid:
        errors['invalid_observation_ids'] = invalid
    cited = [o for o in observations if o.id in refinement.observation_ids and o.id in eligible_ids]
    invalid_targets = sorted({a.target for a in refinement.assertions
        if a.target.startswith('obs_') and a.target not in {o.id for o in cited}})
    if invalid_targets:
        errors['uncited_observation_targets'] = invalid_targets
    # Repository refinements discover criteria from retrieved content. A proposed
    # criterion unsupported by those records must remain unresolved, not become
    # a new grounded requirement that prevents later correction.
    if not check.assertions and all(a.source == 'repository' for a in refinement.assertions):
        if require_content and not any(a.field == 'content' for a in refinement.assertions):
            errors['missing_content_proof'] = 'An explanation requires source content; file existence alone cannot resolve it'
        preview = check.model_copy(update={'assertions': refinement.assertions})
        unsupported = [{'assertion_index': index, 'assertion': r['assertion'],
                        'observation_id': r.get('observation_id'), 'verdict': r['verdict'],
                        'reason': r.get('reason') or 'Cited content does not satisfy the proposed predicate'}
                       for index, r in enumerate(checks.evaluate(preview, cited)) if r['verdict'] != 'passed']
        if unsupported:
            for item in unsupported:
                item['supporting_sources'] = supporting_repository_sources(
                    refinement.assertions[item['assertion_index']], [o for o in observations if o.id in eligible_ids])
            errors['unsupported_assertions'] = unsupported
    return errors


def _admit_plan(spec, discovery, *, runtime_scope=False, default_runtime=False, explicit_targets=(), browser_scope=False):
    """Validate proposed expectations against known execution lifecycles.

    Repository lifecycle metadata is a planning hypothesis, never evidence.
    Accepted service checks still require actual running state AND a live probe.
    Preserve the original proposed plan separately for audit.
    """
    from wizard_kernel.contracts.verification import Assertion
    services = {c["command"] for c in discovery.get("command_candidates", [])
                if c.get("lifecycle") == "long_running"}
    declared_commands = {c["command"] for c in discovery.get("command_candidates", [])}
    adjustments = []
    if default_runtime:
        from wizard_kernel.contracts.verification import CheckSpec
        # The command's baseline contract does not need an LLM to invent a list
        # of repository prerequisites. Explorer still discovers/selects the tool.
        execution = next((c for c in spec.checks if "process" in c.capabilities or any(a.source == "process" for a in c.assertions)), None)
        if execution is None:
            execution = next((c for c in spec.checks if any(a.source == "command" for a in c.assertions)), None)
        if execution is not None:
            # Discovery is already supplied as evidence. A bare command asks
            # for one runtime smoke check, not extra migrations or static gates.
            spec.checks = [execution.model_copy(update={"depends_on": []})]
        else:
            service = bool(services)
            spec.checks = [CheckSpec(id="runtime_smoke", description="Verify application runtime execution",
                capabilities=["process"] if service else [], assertions=[
                    Assertion(source="process", field=field, operator="equals", expected="true")
                    for field in ("is_running", "active")] if service else [
                    Assertion(source="command", field="exit_code", operator="equals", expected="0")])]
        adjustments.append({"check_id": spec.checks[0].id, "reason": "Bare verify runtime checks actual execution; repository discovery is context, not a verification dependency; unrequested additional operations are omitted"})
    for check in spec.checks:
        parents = [c for c in spec.checks if c.id in check.depends_on]
        readback = (check.workflow in {"general", "form_submission"} and any(c.workflow == "form_submission" for c in parents)
                    and re.match(r"\s*(?:verify|confirm|check|observe|ensure|inspect)\b", check.description, re.I)
                    and not re.search(r"\b(?:create|creating|creation|submit|submitting|add|adding)\b", check.description, re.I))
        if readback:
            check.workflow = "general"
            for criterion in check.assertions:
                if criterion.source == "browser":
                    criterion.root.after_submission = False
            adjustments.append({"check_id": check.id, "reason": "Readback observes its dependency's created result; it does not request another form submission"})
        elif check.workflow == "general" and any(a.source == "browser" and a.after_submission for a in check.assertions):
            check.workflow = "form_submission"
        if browser_scope and ("http" in check.capabilities or any(a.source == "http" for a in check.assertions)) and not (
                "process" in check.capabilities or any(a.source in {"process", "command"} for a in check.assertions)):
            if check.workflow == "general" and any(a.source == "http" and a.field == "status_code" and a.expected == "201"
                                                    for a in check.assertions):
                check.workflow = "form_submission"
            check.capabilities = [c for c in check.capabilities if c != "http"]
            check.description = re.sub(r"\b(?:via|using|through)\s+(?:the\s+)?API\b", "through the observed browser UI", check.description, flags=re.I)
            if "browser" not in check.capabilities:
                check.capabilities.append("browser")
            check.assertions = []
            check.unresolved_reason = "User requested browser verification: discover the actual UI operation and its observable outcome; API response predicates cannot verify a browser submission"
            adjustments.append({"check_id": check.id, "reason": "API-only outcome proposal replaced with unresolved browser outcome contract to preserve the explicitly requested browser workflow"})
        if check.workflow in {"registration", "login", "form_submission"}:
            if "browser" not in check.capabilities:
                check.capabilities.append("browser")
            for criterion in check.assertions:
                if criterion.source == "browser":
                    criterion.root.after_submission = True
        inferred_ui = [a for a in check.assertions if a.source == "browser" and not (
            a.field == "url" and a.operator == "equals" and a.expected in explicit_targets)]
        if inferred_ui:
            if "browser" not in check.capabilities:
                check.capabilities.append("browser")
            # Before discovery, the Planner has no page/endpoint observations.
            # A guessed URL/title/label is a proposal, not an immutable contract.
            # Keep the original proposed_plan.json; ground criteria before locking.
            check.assertions = []
            check.unresolved_reason = "Discover the actual endpoint/page contract before defining UI expectations; the initial Planner values were ungrounded proposals"
            adjustments.append({"check_id": check.id, "reason": "Inferred browser expectations deferred to actual discovery; explicit URL-only requirements are retained"})
        unresolved_process_target = any(a.source == "process" and a.target and a.target not in declared_commands for a in check.assertions)
        if unresolved_process_target:
            # A component label is not an executable identity. Keep the proposed
            # contract in proposed_plan.json; bind an accepted one to observed
            # execution instead of locking in an impossible target comparison.
            check.unresolved_reason = "Discover the actual process command and listener, then refine process is_running and active predicates using this check's execution observations; a component label is not a command"
            adjustments.append({"check_id": check.id, "reason": "Unresolved process target deferred to actual execution identity"})
        if check.unresolved_reason and check.assertions:
            adjustments.append({"check_id": check.id, "reason": "Unresolved expectations require discovery; proposed assertions were not accepted"})
            check.assertions = []
        if runtime_scope and set(check.capabilities) == {"process"} and not check.assertions and services and not unresolved_process_target:
            check.assertions = [Assertion(source="process", field=field, operator="equals", expected="true")
                                for field in ("is_running", "active")]
            check.unresolved_reason = ""
            adjustments.append({"check_id": check.id, "reason": "Runtime service readiness is explicit: running state AND an actual owned listener probe"})
        accepted = []
        for assertion in check.assertions:
            if (assertion.source == "command" and assertion.field == "exit_code"
                    and assertion.operator == "equals" and assertion.expected == "0"
                    and assertion.target in services and "process" in check.capabilities):
                accepted.extend([Assertion(source="process", field=field, operator="equals",
                                           expected="true", target=assertion.target)
                                 for field in ("is_running", "active")])
                adjustments.append({"check_id": check.id, "reason": "Declared long-running service requires running state and listener evidence, not a terminating command exit"})
            else:
                accepted.append(assertion)
        check.assertions = accepted
    return adjustments


def _account_dependencies(spec, disposable, *, login_requested=True):
    """A newly generated account must be created before its login is tested."""
    if not disposable:
        return []
    from wizard_kernel.contracts.verification import CheckSpec
    login = [c for c in spec.checks if c.workflow == "login"]
    registration = [c for c in spec.checks if c.workflow == "registration"]
    if registration and login and not login_requested:
        removed = {c.id for c in login}
        spec.checks = [c for c in spec.checks if c.id not in removed]
        for check in spec.checks:
            deps = [d for d in check.depends_on if d not in removed]
            if any(d in removed for d in check.depends_on):
                deps += [c.id for c in registration if c.id != check.id]
            check.depends_on = list(dict.fromkeys(deps))
        VerificationSpec.model_validate(spec.model_dump())
        return [{"check_id": c.id, "reason": "Separate login was not requested; downstream operations use the verified registration session"} for c in login]
    if not login:
        return []
    if not registration:
        prerequisite = CheckSpec(id="prepare_account_" + uuid.uuid4().hex[:8],
            description="Create the authorized disposable local account using the observed application flow",
            workflow="registration", capabilities=["browser"],
            unresolved_reason="Discover actual registration controls and its successful result",
            depends_on=[d for d in login[0].depends_on if d not in {c.id for c in login}])
        spec.checks.append(prerequisite)
        registration = [prerequisite]
    changes = []
    for check in registration:
        check.depends_on = [d for d in check.depends_on if d not in {c.id for c in login}]
    for check in login:
        check.depends_on = list(dict.fromkeys(check.depends_on + [c.id for c in registration]))
        changes.append({"check_id": check.id, "reason": "Disposable account login depends on actual registration verification"})
    VerificationSpec.model_validate(spec.model_dump())  # Preserve unique IDs, DAG and check limit.
    return changes


def _available(check, resources, can_browser, has_values, targets=()):
    sources = {a.source for a in check.assertions} | set(check.capabilities)
    names = {"read_file", "search_files", "list_tree", "path_exists"}
    if sources & {"command", "process", "browser", "http"}:
        names |= {"execute_command", "start_process", "check_port"}
        if resources["processes"]:
            names |= {"read_process", "kill_process"}
    if "http" in sources:
        names.add("http_request")
    if can_browser and "browser" in sources:
        external = any(urlsplit(t).scheme in {"http", "https"} and ToolRequestValidator._endpoint_host(urlsplit(t).hostname or "") != "loopback" for t in targets)
        if resources["reachable_endpoints"] or resources["browser"] or external:
            names.add("browser_navigate")
        if resources["browser"]:
            names |= {"browser_snapshot", "browser_extract", "browser_back"}
            if resources["browser"].get("controls"):
                names.add("browser_click")
                if has_values:
                    names |= {"browser_type", "browser_fill_form"}
                    if (resources.get("form_state") or {}).get("all_filled"):
                        names.discard("browser_fill_form")
        # Startup has its own checks. A live UI check doesn't need schemas for
        # starting arbitrary additional services or executing unrelated commands.
        # Read/probe tools remain available; a failed endpoint re-enables startup.
        if not sources & {"process", "command"} and resources["reachable_endpoints"]:
            names -= {"execute_command", "kill_process", "list_tree", "path_exists"}
    return sorted(names)


def _repository_report(inv, state):
    if state.get("report_source"):
        previous = fs_store.read_text(state["report_source"], "verification_report.md")
        if previous is not None:
            return "Saved report from " + state["report_source"] + "; no new verification was executed.\n\n" + previous
    def text(value):
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    def witness(assertion):
        observed = str(assertion["actual"])
        expected = str(assertion.get("assertion", {}).get("expected", ""))
        sensitive = assertion.get('assertion', {}).get('case_sensitive', True)
        offset = (observed if sensitive else observed.casefold()).find(expected if sensitive else expected.casefold()) if expected and assertion.get("verdict") == "passed" else -1
        start = max(0, offset - 40)
        return ("…" if start else "") + observed[start:start + max(180, len(expected) + 40)]
    lines = ["# Wizard verification report", "", f"Request: {text(flow_trace.safe_text(inv.question or " ".join([inv.intent, *inv.targets]), limit=8000))}",
             f"Investigation: `{inv.id}`", f"State: {inv.state.value}",
             f"Decision requests: {state['model_calls']}", f"Provider HTTP attempts: {state.get('provider_requests', 0)}",
             f"Evidence memory: {state.get('memory', {}).get('claims', 0)} claims; {state.get('memory', {}).get('observations', 0)} observations; {state.get('memory', {}).get('investigation_nodes', 0)} investigation nodes",
             "", "| Check | Expected | Observed | Verdict | Evidence / blocker |",
             "|---|---|---|---|---|"]
    for check in state.get("checks", []):
        result = state["results"].get(check["id"], {})
        assertions = result.get("assertions", [])
        expected = "; ".join(f"{a['field']} {a['operator']} {a['expected']}" for a in check["assertions"]) or "Unspecified: discovery required"
        observed = "; ".join(witness(a) for a in assertions if a.get("actual") is not None)
        refs = ", ".join(a["observation_id"] for a in assertions if a.get("observation_id"))
        reason = "; ".join(a.get('reason', '') for a in assertions if a.get('verdict') != 'passed' and a.get('reason')) or result.get("reason") or ""
        evidence = "; ".join(part for part in (refs, reason) if part)
        label = {'passed': 'PASS', 'failed': 'FAIL', 'evaluation_error': 'EVALUATION ERROR'}.get(result.get('status'), 'UNVERIFIED')
        fallback = 'Evaluation failed' if result.get('status') == 'evaluation_error' else 'Not observed'
        lines.append(f"| {text(check['description'])} | {text(expected)} | {text(observed or fallback)} | "
                     f"{label} | {text(evidence or 'Not evaluated')} |")
    if state.get("plan_adjustments"):
        lines.extend(["", "Plan admission:"])
        lines.extend(f"- {text(item['check_id'])}: {text(item['reason'])}" for item in state["plan_adjustments"])
    if state.get('architecture_findings'):
        lines += ['', '## Architecture findings', '']
        for finding in state['architecture_findings']:
            check_id = state.get('architecture_coverage_ids', {}).get(finding['area'], 'architecture_' + finding['area'])
            result = state['results'].get(check_id, {})
            if result.get('status') == 'passed':
                refs = ', '.join(dict.fromkeys(a['observation_id'] for a in result['assertions'] if a.get('observation_id')))
                lines.append(f"- **{text(finding['area'])}**: {text(finding['summary'])} (evidence: {text(refs)})")
            else:
                lines.append(f"- **{text(finding['area'])}**: unresolved — {text(finding.get('blocker') or 'Content proof did not pass; see verification table')}")
    if state.get("stop_reason"):
        lines += ["", "Stopped: " + text(state["stop_reason"])]
    lines += ["", "Cleanup: " + text(state.get("cleanup", "Pending")), "",
              "Local process execution uses the configured sandbox; it is not container isolation."]
    return "\n".join(lines) + "\n"


def _render(inv, state):
    if inv.intent in {"explain", "investigate"}:
        report = _repository_report(inv, state)
        for finding in state.get('repository_findings', {}).values():
            report += '\n\nRepository finding: ' + finding['summary'] + '\n'
        return report

    if state.get("report_source"):
        previous = fs_store.read_text(state["report_source"], "verification_report.md")
        if previous is not None:
            return "Saved report from " + state["report_source"] + "; no new verification was executed.\n\n" + previous
    from wizard_kernel.control.runbook import markdown, project
    return markdown(project(inv, state))


def run(inv, manager, policy=None, *, browser_factory=None):
    """Normal API entry point. Injecting a policy is only for provider-free tests."""
    import os
    from wizard_kernel.world import browser as browsers
    if fs_store.read(inv.id, "verification.json") is not None:
        return  # Never overwrite/replay a durably accepted investigation.
    bus = events.create(inv.id)
    kg = KnowledgeGraph(inv.id)
    graph = InvestigationGraph(inv.id)
    register_graph(inv.id, graph)
    evidence = EvidenceEngine(kg)

    def index_observation(obs):
        node = graph.get(obs.node_id)
        if node is None:
            node = InvestigationNode(id=obs.node_id, type="browser" if obs.source_tool.startswith("browser_") else
                                     "read" if obs.source_tool in {"read_file", "list_tree", "search_files"} else "execute",
                                     action={"tool": obs.source_tool}, goal_id=obs.goal_id,
                                     hypothesis=Hypothesis(kind=HypothesisKind.always_success))
            graph.add(node)
        claim_ids = []
        # Failure observations never claim that an operation succeeded.
        if obs.success:
            candidates = extractors.extract(obs)
            data = obs.payload.get("data") or {}
            if obs.source_tool == "read_file":
                candidates.append(extractors.ExtractResult("FILE_READ", str(data.get("path") or obs.node_id),
                    {"content_sha256": hashlib.sha256(str(data.get("content") or "").encode()).hexdigest()}))
            elif obs.source_tool in {"start_process", "read_process", "http_request"}:
                for field in ("handle_id", "is_running", "exit_code", "status_code"):
                    if data.get(field) is not None:
                        candidates.append(extractors.ExtractResult("RUNTIME", field, data[field]))
            for fact in candidates:
                # Mutable page/process state is scoped to an observation, so a
                # legitimate navigation is not recorded as a contradiction.
                tier = trust.source_tier_for_tool(obs.source_tool)
                if tier == "execution":
                    key = obs.id + ":" + fact.key
                else:
                    source_path = str(data.get("path") or (obs.payload.get("meta") or {}).get("path") or "")
                    key = source_path + ":" + fact.key if source_path and fact.claim_type != "FILE_READ" else fact.key
                admitted = evidence.admit(inv_id=inv.id, claim_type=fact.claim_type, key=key,
                    value=_redact(fact.value, authorized, public_refs), obs_id=obs.id, support_type=fact.support_type,
                    source_tier=tier, node_id=obs.node_id)
                if admitted:
                    claim_ids.append(admitted[0].id)
        graph.set_state(obs.node_id, "complete" if obs.success else "failed", obs_ids=[obs.id], claim_ids=claim_ids)
        kg.persist()
        graph.persist()

    store = ObservationStore(inv.id, on_append=index_observation)
    sandbox = get_sandbox(inv.options.get("sandbox_mode", "local_dev"))
    browser = None
    validator = ToolRequestValidator(inv.repository_path, inv.options.get("allowed_domains", []), False, navigation_targets=inv.targets)
    state = {"version": 2, "checks": [], "results": {}, "executions": [], "model_calls": 0,
             "decisions": [], "cleanup": "Pending", "stop_reason": ""}
    deadline = time.monotonic() + inv.options.get("max_elapsed_seconds", 600)
    max_calls = inv.options.get("max_model_calls", 24)
    max_input = inv.options.get("max_input_chars", 60000)
    authorized = {}
    public_refs = ()

    def active():
        return [{"id": c["id"], "name": c["description"],
                 "state": {"passed": "satisfied", "failed": "failed"}.get(state["results"].get(c["id"], {}).get("status"), "open"),
                 "status": state["results"].get(c["id"], {}).get("status", "unverified").upper(),
                 "progress": sum(a["verdict"] == "passed" for a in state["results"].get(c["id"], {}).get("assertions", [])) / max(1, len(c["assertions"]))}
                for c in state["checks"]]

    last_report_digest = None

    def write_report(target):
        nonlocal last_report_digest
        from wizard_kernel.control.runbook import persist, markdown
        data = persist(target, state)
        report = _render(target, state) if state.get("report_source") or inv.intent in {"investigate", "explain"} else markdown(data)
        digest = hashlib.sha256(report.encode()).hexdigest()
        if digest != last_report_digest:
            fs_store.write_text(inv.id, "verification_report.md", report)
            last_report_digest = digest
            bus.emit(events.ReportUpdated, {"revision": digest})

    def save(**update):
        state["memory"] = {"claims": len(kg.all_claims()), "investigation_nodes": len(graph.all_nodes()),
                           "observations": store.count()}
        for check in state["checks"]:
            checkpoint = graph.get("check_" + check["id"])
            if checkpoint:
                graph.add(checkpoint.model_copy(update={"action": {"description": check["description"], "assertions": check["assertions"]}}))
                status = state["results"].get(check["id"], {}).get("status")
                graph.set_state(checkpoint.id, {"passed": "complete", "failed": "failed", "unverified": "blocked"}.get(status, "waiting"))
        graph.persist()
        kg.persist()
        if update.get("state") and is_terminal(update["state"]):
            final = update.pop("state")
            def persist_result(actual_state):
                fs_store.write(inv.id, "verification.json", state)
                write_report(replace(inv, state=actual_state))
            return manager.finalize(inv.id, final, persist_result, active_goals=active(), **update)
        else:
            manager.update(inv.id, active_goals=active(), **update)
            fs_store.write(inv.id, "verification.json", state)
            write_report(inv)

    def guard():
        if inv.cancel_requested or inv.state == LifecycleState.cancelled:
            raise InterruptedError("Cancelled by user")
        if time.monotonic() >= deadline:
            raise InterruptedError("Investigation elapsed-time budget exhausted")

    def request(role, context, model):
        guard()
        if state["model_calls"] >= max_calls:
            raise InterruptedError("Model decision budget exhausted")
        context, selection, _ = prepare_context(role, context, model, max_input)
        state.setdefault("context_selection", []).append({"agent": role, **selection})
        raw = json.dumps(context, sort_keys=True, default=str)
        identity = hashlib.sha256((role + raw).encode()).hexdigest()
        if identity in state["decisions"]:
            raise InterruptedError("No progress: this decision context was already requested")
        state["decisions"].append(identity)
        state["model_calls"] += 1
        state["last_agent"] = role
        save(last_event=f"{role} decision requested")
        bus.emit(events.AgentConsulted, {"agent_type": role})
        flow_trace.record(inv.id, role + ".request", check_id=context.get("current_check", {}).get("id"),
                          context_chars=len(raw), fingerprint=identity, model_calls=state["model_calls"])
        def progress(stage, details):
            state["provider_progress"] = {"agent": role, "stage": stage, **details}
            save(last_event=f"{role}: provider {stage}")
            bus.emit("provider.progress", state["provider_progress"])
        from wizard_kernel.storage.usage import operation
        with operation(inv):
            result = policy.request(role, context, model, max_input_chars=max_input, cancel_check=guard,
                                    deadline=deadline, on_progress=progress)
        state["provider_requests"] = getattr(policy, "provider_requests", 0)
        state["provider_metadata"] = getattr(policy, "last_metadata", {})
        # Persist a successfully validated response even if cancellation arrived
        # during HTTP. Cancellation still prevents any downstream execution.
        if role == "planner":
            fs_store.write(inv.id, "recovery_plan.json" if context.get("recovery_request") else "plan.json", _redact(result.model_dump(), authorized, public_refs))
        flow_trace.record(inv.id, role + ".response", response_model=model.__name__)
        if role == "explorer":
            state.setdefault("decision_results", []).append({"context_hash": identity,
                "check_id": context.get("current_check", {}).get("id"),
                "response": _redact(result.model_dump(), authorized, public_refs)})
            save()
        bus.emit("agent.completed", {"agent_type": role, "response_model": model.__name__})
        guard()
        return result

    def execute(tool, proposed, params, check_id, purpose="agent"):
        guard()
        if inv.budget_remaining <= 0:
            raise InterruptedError("Tool execution budget exhausted")
        execution = {"id": uuid.uuid4().hex, "check_id": check_id, "tool": tool,
                     "parameters": flow_trace.safe_parameters(proposed), "state": "accepted", "accepted_at": time.time(), "purpose": purpose}
        state["executions"].append(execution)
        graph.add(InvestigationNode(id=execution["id"], type="browser" if tool.startswith("browser_") else
                  "read" if tool in {"read_file", "search_files", "list_tree"} else "execute", goal_id=check_id,
                  state="running", action={"tool": tool, "params": flow_trace.safe_parameters(proposed)},
                  hypothesis=Hypothesis(kind=HypothesisKind.always_success)))
        save(last_event=f"Executing {tool}")
        bus.emit(events.NodeStarted, {"node_id": execution["id"], "type": "browser" if tool.startswith("browser_") else "execute",
                                      "tool": tool, "params": flow_trace.safe_parameters(proposed), "goal_id": check_id})
        guard()
        if tool in {"start_process", "execute_command"} and hasattr(sandbox, "output_callback"):
            sandbox.output_callback = _process_output_sink(bus, execution["id"], check_id,
                lambda text: _redact(text, authorized, public_refs),
                max((len(v) for k, v in authorized.items() if k not in public_refs), default=0))
        payload = _redact(tools.execute({"tool": tool, "params": params}), authorized, public_refs)
        if "url" in params:
            payload.setdefault("meta", {})["target_url"] = flow_trace.safe_parameters({"url": params["url"]})["url"]
        obs = store.append(node_id=execution["id"], goal_id=check_id, source_tool=tool,
                           obs_type="artifact" if tool == "browser_screenshot" else _TOOL_TO_OBS_TYPE.get(tool, "command_result"), payload=payload,
                           tool_request_id=execution["id"], execution_id=execution["id"])
        validator.record_execution(tool, params, payload, obs.id)
        execution.update(state="observed", observation_id=obs.id, success=obs.success, finished_at=time.time())
        if tool == "browser_screenshot" and obs.success:
            state.setdefault("artifacts", []).append({**payload["data"], "observation_id": obs.id, "goal_id": check_id, "execution_id": execution["id"]})
        execution["result_fingerprint"] = hashlib.sha256(json.dumps([tool, payload], sort_keys=True, default=str).encode()).hexdigest()
        inv.budget_remaining -= 1
        inv.nodes_completed += 1
        bus.emit(events.NodeCompleted if obs.success else events.NodeFailed,
                 {"node_id": execution["id"], "tool": tool, "ok": obs.success, "observation_id": obs.id})
        _emit_tool_observed(bus, obs)
        if tool == "start_process" and payload.get("ok"):
            node = InvestigationNode(id=execution["id"], type="execute", action={},
                                     hypothesis=Hypothesis(kind=HypothesisKind.always_success))
            _probe_started_process(tools, store, node, check_id, payload, validator=validator,
                                   timeout_seconds=max(0, min(20, deadline-time.monotonic())), cancel_check=guard,
                                   sanitize=lambda p: _redact(p, authorized, public_refs), bus=bus)
        if tool.startswith("browser_") and tool != "browser_screenshot" and payload.get("ok"):
            _emit_browser_narration(bus, tool, payload.get("data") or {}, page=_current_page(tools))
        save()
        if tool.startswith("browser_") and tool != "browser_screenshot" and not obs.success:
            capture_screenshot(check_id, failure=True)
        return obs

    def capture_screenshot(check_id, *, failure=False):
        mode = inv.options.get("screenshots", "off")
        if mode == "off" or (not failure and mode != "checkpoints") or not browser or not browser.started:
            return
        if state.get("screenshot_attempts", 0) >= inv.options.get("max_screenshots", 4) or inv.budget_remaining <= 0:
            return
        checked = validator.validate(ToolRequest(tool="browser_screenshot", parameters={}), inv.budget_remaining)
        if checked.valid:
            state["screenshot_attempts"] = state.get("screenshot_attempts", 0) + 1
            execute("browser_screenshot", {}, checked.sanitised_params, check_id, purpose="artifact")

    def refresh_processes(check):
        for process in sandbox.list_processes():
            params = {"handle_id": process.handle_id}
            checked = validator.validate(ToolRequest(tool="read_process", parameters=params), inv.budget_remaining)
            if not checked.valid:
                continue
            current = _redact(tools.execute({"tool": "read_process", "params": params}), authorized, public_refs)
            validator.record_execution("read_process", params, current)
            goal_id = check.id if any(a.source == "process" for a in check.assertions) else None
            previous = next((o for o in reversed(store.all()) if o.source_tool == "read_process" and o.goal_id == goal_id
                             and (o.payload.get("meta") or {}).get("handle_id") == process.handle_id), None)
            if previous is None or previous.payload != current:
                observed = store.append(node_id="resource_state", goal_id=goal_id,
                             source_tool="read_process", obs_type="command_result", payload=current, execution_id=uuid.uuid4().hex)
                _emit_tool_observed(bus, observed)

    try:
        guard()
        save(state=LifecycleState.scanning, last_event="Discovering repository")
        if inv.intent == "report":
            previous = sorted((v for v in manager.all() if v.id != inv.id and v.repository_path == inv.repository_path
                               and fs_store.report_path(v.id).exists()), key=lambda v: v.updated_at)
            if previous:
                state["report_source"] = previous[-1].id
            else:
                state["stop_reason"] = "No saved investigation report exists for this repository; no new verification was performed"
            save(state=LifecycleState.reporting)
        else:
            from wizard_kernel.world import repository
            repository.validate(inv.repository_path)
            manifest = scanner.scan(inv.repository_path, inv.id)
            fs_store.write(inv.id, "manifest.json", manifest.model_dump())
            authorized = json.loads(os.environ.get("WIZARD_TEST_DATA_JSON", "{}"))
            if not isinstance(authorized, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in authorized.items()):
                raise ValueError("WIZARD_TEST_DATA_JSON must map input references to strings")
            if not authorized:
                authorized = _local_test_inputs(inv)
                public_refs = tuple(key for key in ("text", "description") if key in authorized)
                state["test_input_source"] = "disposable_local" if authorized else "unavailable"
            else:
                state["test_input_source"] = "configured"
            policy = policy or ModelPolicy()
            # Read actual project contracts, not just filename heuristics. The
            # existing validated file executor works before process provisioning.
            sandbox.start(inv.repository_path)
            reader = ToolExecutor(sandbox, inv.repository_path)
            documents = []
            candidates = sorted(manifest.key_files, key=lambda p: (not Path(p).name.lower().startswith("readme"), len(Path(p).parts)))
            if inv.intent == 'investigate' and 'architecture' in inv.targets:
                from wizard_kernel.control.architecture_coverage import discovery_paths
                candidates = discovery_paths(manifest.key_files)
            for path in candidates[:8]:
                if Path(path).suffix.lower() in {".blend", ".sln"}:
                    continue
                params = {"path": path, "max_bytes": 3000}
                validation = validator.validate(ToolRequest(tool="read_file", parameters=params), max(1, inv.budget_remaining))
                if not validation.valid:
                    continue
                payload = _redact(reader.execute({"tool": "read_file", "params": validation.sanitised_params}), authorized, public_refs)
                obs = store.append(node_id="discovery_" + uuid.uuid4().hex[:10], source_tool="read_file",
                                   obs_type="file_content", payload=payload, evidence_categories=["repository_read"])
                validator.record_execution("read_file", validation.sanitised_params, payload, obs.id)
                if obs.success:
                    documents.append({"path": path, "observation_id": obs.id,
                                      "content": (payload.get("data") or {}).get("content", "")[:3000]})
            discovery = {"key_files": manifest.key_files[:30],
                         "extensions": manifest.extensions, "documents": documents,
                         "command_candidates": _discover_runnable_commands(inv.repository_path)}
            save(state=LifecycleState.planning)
            planning_discovery = discovery
            if inv.intent == 'investigate' and 'architecture' in inv.targets:
                planning_discovery = {**discovery, 'documents': [
                    {**d, 'content': d['content'][:1000]} for d in discovery['documents']]}
            planning_context = {"original_request": flow_trace.safe_text(_redact(_effective_request(inv), authorized, public_refs), limit=8000),
                                      "command_family": inv.intent, "targets": inv.targets, "discovery": planning_discovery,
                                      "knowledge": [{"id": c.id, "type": c.claim_type, "key": c.key, "value": c.value}
                                                    for c in kg.all_claims()[:16]],
                                      "authorized_value_refs": list(authorized)}
            plan_model = planning_model([c['command'] for c in discovery['command_candidates']], read_only=inv.intent == 'explain',
                repository_targets=[v for d in discovery['documents'] for v in (d['path'], d['observation_id'])])
            for attempt in range(2):
                spec = request('planner', planning_context, plan_model)
                feedback = []
                architecture_plan = inv.intent == 'investigate' and 'architecture' in inv.targets
                if inv.intent == 'explain' or architecture_plan:
                    from wizard_kernel.contracts.verification import CheckSpec
                    # These are proposals, not admitted requirements yet. Reject
                    # invented content before it becomes an immutable predicate.
                    for proposed_check in spec.checks:
                        proposed_check = CheckSpec.model_validate(proposed_check.model_dump())
                        for index, result in enumerate(checks.evaluate(proposed_check, store.all())):
                            # Architecture discovery may legitimately need more
                            # reads. Reject only claims already contradicted by
                            # supplied content before admitting them as goals.
                            unsupported = result['verdict'] != 'passed' if inv.intent == 'explain' else result['verdict'] == 'failed'
                            if unsupported:
                                feedback.append({'check_id': proposed_check.id, 'assertion_index': index,
                                    'assertion': result['assertion'], 'verdict': result['verdict'],
                                    'observation_id': result.get('observation_id'),
                                    'reason': result.get('reason') or 'Proposed content is not supported by the supplied document',
                                    'supporting_sources': supporting_repository_sources(proposed_check.assertions[index], store.all())})
                    history_key = 'explanation_plan_attempts' if inv.intent == 'explain' else 'architecture_plan_attempts'
                    state.setdefault(history_key, []).append({'proposal': spec.model_dump(), 'feedback': feedback})
                if not feedback:
                    break
                if attempt == 1:
                    label = 'Explanation' if inv.intent == 'explain' else 'Architecture'
                    raise InterruptedError(label + ' plan remains unsupported by observed content after one correction')
                planning_context['planning_feedback'] = feedback
                planning_context['correction_instruction'] = ('The proposed content criteria were not grounded and have not been admitted. '
                    'Preserve the original request as repository discovery goals with assertions=[] and a precise unresolved_reason. '
                    'The Explorer must inspect actual observations before proposing content criteria. Do not invent replacement literals.')
                plan_model = planning_model([], read_only=True, discovery_only=True)
            spec = VerificationSpec.model_validate(spec.model_dump())
            fs_store.write(inv.id, "proposed_plan.json", spec.model_dump())
            state["effective_request"] = _effective_request(inv)
            state["plan_adjustments"] = _admit_plan(spec, discovery,
                runtime_scope=inv.intent == "verify" and "runtime" in inv.targets,
                default_runtime=inv.intent == "verify" and "runtime" in inv.targets and not inv.question.strip(),
                explicit_targets=inv.targets,
                browser_scope="browser" in inv.question.casefold() and not re.search(r"\b(?:api|endpoints?)\b", inv.question, re.I))
            state["plan_adjustments"] += _account_dependencies(spec, state.get("test_input_source") == "disposable_local",
                login_requested=not inv.question.strip() or bool(re.search(r"\b(?:login|log\s*in|sign\s*in)\b", inv.question, re.I)))
            state["checks"] = spec.model_dump()["checks"]
            for check in spec.checks:
                graph.add(InvestigationNode(id="check_" + check.id, type="checkpoint", goal_id=check.id,
                    action={"description": check.description, "assertions": [a.model_dump() for a in check.assertions]},
                    depends_on=["check_" + d for d in check.depends_on], hypothesis=Hypothesis(kind=HypothesisKind.manual_escalate)))
            graph.persist()
            fs_store.write(inv.id, "plan.json", spec.model_dump())
            can_execute = inv.options.get("allow_execution")
            if can_execute is None:
                can_execute = inv.intent != "explain"
            needs_browser = can_execute and any("browser" in c.capabilities or any(a.source == "browser" for a in c.assertions) for c in spec.checks)
            can_browser = needs_browser and inv.options.get("allow_browser") is not False
            if can_browser:
                inv.options["browser_enabled"] = True
                browser = (browser_factory or browsers.get_browser)(inv.options)
                browsers.register_runtime(inv.id, browser)
                validator._browser_enabled = True
            tools = ToolExecutor(sandbox, inv.repository_path, browser=browser, investigation_id=inv.id,
                                 private_capture=state.get("test_input_source") == "configured" and bool(authorized))
            if inv.intent == 'investigate' and 'architecture' in inv.targets:
                from wizard_kernel.control.architecture_coverage import candidates, imports, balanced_evidence, boundary, source_path
                def architecture_evidence():
                    return balanced_evidence(store.all())

                # Strategic coverage remains inside this investigation and its
                # existing tool budget, validator, observations and deadline.
                known_paths = {p.replace('\\', '/') for p in manifest.directory_tree}
                read_paths = {(o.payload.get('data') or {}).get('path', '').replace('\\', '/')
                              for o in store.all() if o.success and o.source_tool == 'read_file'}
                selected = candidates(known_paths, read_paths)
                allowance = min(28, max(0, inv.budget_remaining - 4))
                for path in selected[:allowance]:
                    params = {'path': path, 'max_bytes': 6000}
                    checked = validator.validate(ToolRequest(tool='read_file', parameters=params), inv.budget_remaining)
                    if checked.valid:
                        execute('read_file', params, checked.sanitised_params,
                                'architecture_coverage', purpose='architecture_repository_coverage')
                # Follow references into missed layers, not arbitrary extra files.
                read_rows = [{'path': (o.payload.get('data') or {}).get('path', '').replace('\\', '/'),
                              'content': str((o.payload.get('data') or {}).get('content', ''))}
                             for o in store.all() if o.success and o.source_tool == 'read_file']
                inspected = {r['path'] for r in read_rows}
                missing_imports = sorted({target for row in read_rows
                    for target, _, _ in imports(row['path'], row['content'], known_paths)
                    if target not in inspected and target in selected})
                for path in missing_imports[:min(4, max(0, inv.budget_remaining - 1))]:
                    params = {'path': path, 'max_bytes': 6000}
                    checked = validator.validate(ToolRequest(tool='read_file', parameters=params), inv.budget_remaining)
                    if checked.valid:
                        execute('read_file', params, checked.sanitised_params,
                                'architecture_coverage', purpose='architecture_import_followup')
                inspected = {r['path'] for r in architecture_evidence()}
                missing = [p for p in selected if p not in inspected]
                state['architecture_coverage'] = {'candidate_files': len(selected),
                    'inspected_files': sorted(inspected), 'uninspected_files': missing,
                    'unrepresented_boundaries': sorted({boundary(p)[1] for p in selected} -
                                                       {boundary(p)[1] for p in inspected}),
                    'strategy': 'bounded layer representatives and literal local imports'}

            save(state=LifecycleState.investigation_loop)
            bus.emit(events.InvestigationStarted, {"repository_path": inv.repository_path})
            ordered, remaining = [], list(spec.checks)
            while remaining:
                ready = next(c for c in remaining if all(d in {x.id for x in ordered} for d in c.depends_on))
                ordered.append(ready)
                remaining.remove(ready)
            def run_check(check):
                guard()
                if inv.intent == 'investigate' and 'architecture' in inv.targets and not check.assertions:
                    state['results'][check.id] = {'status': 'unverified', 'reason': 'Repository evidence collected; awaiting architecture synthesis'}
                    save()
                    return
                if not can_execute and (set(check.capabilities) - {"repository"} or any(a.source != "repository" for a in check.assertions)):
                    state["results"][check.id] = {"status": "unverified", "reason": "Execution capability disabled for this request"}
                    save()
                    return
                if not can_browser and ("browser" in check.capabilities or any(a.source == "browser" for a in check.assertions)):
                    state["results"][check.id] = {"status": "unverified", "reason": "Browser capability explicitly disabled"}
                    save()
                    return
                if any(state["results"].get(dep, {}).get("status") != "passed" for dep in check.depends_on):
                    state["results"][check.id] = {"status": "unverified", "reason": "Required check dependency did not pass"}
                    save()
                    return
                rejected = state.setdefault("rejected_actions", {}).setdefault(check.id, {})
                stalled_page = None
                def resource_identity():
                    current = _resources(store.all())
                    current["dependency_results"] = {dep: state["results"].get(dep, {}).get("status")
                                                     for dep in check.depends_on}
                    for endpoint in current["reachable_endpoints"]:
                        endpoint.pop("observation_id", None)
                    return _state_identity(current)
                while inv.budget_remaining > 0:
                    guard()
                    # Inspect known handles deterministically before each model
                    # decision; historical process liveness is not current state.
                    refresh_processes(check)
                    results = checks.evaluate(check, store.all())
                    if checks.verdict(results) == "evaluation_error":
                        state["results"][check.id] = {"status": "evaluation_error", "assertions": results,
                            "reason": "; ".join(r.get("reason", "") for r in results)}
                        save()
                        return
                    if checks.verdict(results) == "passed":
                        state["results"][check.id] = {"status": "passed", "assertions": results}
                        save()
                        bus.emit(events.GoalSatisfied, {"goal_id": check.id, "goal_name": check.description})
                        if "browser" in check.capabilities or any(a.source == "browser" for a in check.assertions):
                            capture_screenshot(check.id)
                        break
                    available = _available(check, _resources(store.all()), can_browser, bool(authorized), inv.targets)
                    if inv.options.get("screenshots", "off") != "off" and _resources(store.all())["browser"] and state.get("screenshot_attempts", 0) < inv.options.get("max_screenshots", 4):
                        available = sorted(set(available) | {"browser_screenshot"})
                    current_page = _resources(store.all())['browser']
                    page_identity = _state_identity(current_page)
                    browser_read_stalled = stalled_page is not None and stalled_page == page_identity
                    if browser_read_stalled:
                        available = [t for t in available if t not in {'browser_snapshot', 'browser_extract'}]
                    auth_check = check.workflow in {"registration", "login", "form_submission"}
                    browser_grounded = any(o.goal_id == check.id and o.success and o.source_tool.startswith("browser_")
                                           for o in store.all())
                    context = _context(inv, check, results, store.all(), available, discovery, authorized, public_refs)
                    if state.get("recovery_round"):
                        context["recovery"] = {"round": 1, "reason": state["recovery_round"]["reason"],
                                               "new_dependencies": state["recovery_round"]["dependencies"].get(check.id, [])}
                    if browser_read_stalled:
                        context['browser_state_feedback'] = 'Repeated browser reads returned the same page. The requested URL is not proof the requested form is displayed. Use the actual observed controls or clarify an expected state with browser_assertion; another identical snapshot provides no new evidence.'
                    relevant_ids = {o.id for o in store.all() if o.goal_id == check.id or o.source_tool == "read_file"}
                    context["knowledge"] = [{"id": c.id, "type": c.claim_type, "key": c.key,
                        "value": flow_trace.safe_text(json.dumps(_redact(c.value, authorized, public_refs), default=str), limit=350),
                        "observation_ids": [oid for e in kg.evidence_for(c.id) for oid in e.observation_ids][-2:]}
                        for c in kg.all_claims() if any(oid in relevant_ids for e in kg.evidence_for(c.id) for oid in e.observation_ids)][-8:]
                    context["investigation_graph"] = {"current_goal": check.id, "depends_on": check.depends_on,
                                                     "recent_actions": graph.frontier(limit=3)}
                    progress = context.get("authentication_progress") or {}
                    if not check.assertions and progress.get("submitted"):
                        # Assess a completed write before permitting another write.
                        # Otherwise an unresolved outcome can create duplicate records.
                        available = [t for t in available if t not in {
                            "browser_click", "browser_type", "browser_fill_form", "browser_navigate", "browser_back"}]
                        context["available_tools"] = available
                        context["browser_tool_usage"] = {k: v for k, v in context["browser_tool_usage"].items() if k in available}
                    if not check.assertions and progress.get("result_observation_ids"):
                        # A fresh result snapshot already exists. Reading it again
                        # cannot resolve unspecified outcome predicates.
                        available = [t for t in available if t not in {"browser_snapshot", "browser_extract"}]
                        context["available_tools"] = available
                        context["browser_tool_usage"] = {k: v for k, v in context["browser_tool_usage"].items() if k in available}
                        progress["next_objective"] = "The fresh post-submission result is already observed. Resolve the requested outcome using refine and the result_observation_ids, or inspect relevant repository contracts if its meaning is unknown. Do not repeat snapshots or claim success merely because the page changed."
                    eligible = [o.id for o in store.all() if o.success and
                        (not auth_check or o.goal_id == check.id and o.source_tool.startswith('browser_'))]
                    context['refinement_observation_ids'] = eligible
                    process_only = set(check.capabilities) == {"process"}
                    process_commands = [p["command"] for p in context["resource_state"]["processes"] if p.get("command")]
                    outcome_review = bool(not check.assertions and browser_grounded and progress.get("result_observation_ids"))
                    if outcome_review:
                        context["decision_contract"] = {
                            "phase": "assess_observed_submission_result",
                            "instruction": "The form was already filled and submitted successfully as an operation, not yet verified as an outcome. Interaction tools are temporarily withheld to prevent duplicate submission; they are NOT unavailable capabilities. Return kind=refine with browser assertions for the requested result grounded in the current observed page and result_observation_ids. Use after_submission=true. If the result is unclear, inspect repository contracts with the available read tools. Do not request another submission or report missing interaction capability.",
                            "observation_ids": progress["result_observation_ids"],
                        }
                    model = decision_model(available, allow_evaluate=bool(check.assertions) and (checks.verdict(results) != "unverified" or inv.intent in {"explain", "investigate"}), value_refs=list(authorized),
                                           allow_refine=not check.assertions and (not auth_check or browser_grounded) and (not process_only or bool(process_commands)),
                                           browser_refinement="browser" in check.capabilities or any(a.source == "browser" for a in check.assertions),
                                           allow_blocked=not outcome_review and not (not check.assertions and not _resources(store.all())["browser"]
                                                              and "browser_navigate" in available),
                                           browser_targets=[(_resources(store.all())["browser"] or {}).get("url", "")],
                                           require_submission=auth_check,
                                           process_targets=process_commands if process_only else None,
                                           repository_refinement=set(check.capabilities) == {'repository'},
                                           observation_ids=eligible,
                                           repository_targets=[value for o in store.all() if o.success and o.source_tool == 'read_file'
                                               for value in (o.id, (o.payload.get('data') or {}).get('path')) if value]
                                               if set(check.capabilities) == {'repository'} else None)
                    decision = request("explorer", context, model)
                    refresh_processes(check)
                    results = checks.evaluate(check, store.all())
                    if decision.kind == "refine":
                        from wizard_kernel.contracts.verification import CheckRefinement
                        refinement = CheckRefinement.model_validate(decision.refinement.model_dump())
                        known = {o.id for o in store.all() if o.success}
                        observed_urls = {((o.payload.get("data") or {}).get("page_observation") or o.payload.get("data") or {}).get("url")
                                         for o in store.all() if o.success and o.goal_id == check.id and o.source_tool.startswith("browser_")}
                        observed_commands = {(o.payload.get("data") or {}).get("command")
                                             for o in store.all() if o.success and o.goal_id == check.id
                                             and o.source_tool in {"start_process", "read_process"}}
                        process_grounded = all(a.source != "process" or not a.target or a.target in observed_commands
                                               for a in refinement.assertions)
                        observed_controls = {(c.get("role"), c.get("name")) for o in store.all()
                            if o.success and o.goal_id == check.id and o.id in refinement.observation_ids
                            for c in ((o.payload.get("data") or {}).get("page_observation") or o.payload.get("data") or {}).get("controls", [])}
                        controls_grounded = all(a.field not in {"visible", "enabled", "count"}
                                                or (a.role, a.name) in observed_controls for a in refinement.assertions)
                        if check.unresolved_reason.startswith("Discover the actual process command and listener"):
                            process_grounded = process_grounded and {"is_running", "active"} <= {
                                a.field for a in refinement.assertions if a.source == "process"
                                and a.operator == "equals" and a.expected == "true" and a.target in observed_commands}
                        if auth_check:
                            known = {o.id for o in store.all() if o.success and o.goal_id == check.id
                                     and o.source_tool.startswith("browser_")}
                        details = refinement_errors(check, refinement, store.all(), known, require_content=inv.intent == 'explain')
                        if (details or decision.action is not None or refinement is None or not process_grounded or not controls_grounded
                                or not set(refinement.observation_ids) <= known
                                or any(a.source == "browser" and a.target and a.target not in observed_urls for a in refinement.assertions)):
                            reason = "Refinement rejected: " + json.dumps(details or {"resource_scope": "Use actual observation IDs and observed targets"}, sort_keys=True)
                            fingerprint = hashlib.sha256(decision.model_dump_json().encode()).hexdigest()
                            if rejected.get(fingerprint) == resource_identity():
                                raise InterruptedError("No progress: identical rejected refinement repeated")
                            rejected[fingerprint] = resource_identity()
                            store.append(node_id=check.id, goal_id=check.id, source_tool="explorer", obs_type="agent_failure",
                                         payload={"ok": False, "reason": reason, "details": details, "available_observation_ids": sorted(known)})
                            bus.emit(events.ToolRejected, {"tool": "refine", "node_id": check.id, "reason": reason})
                            save(last_event=reason)
                            continue
                        if check.workflow in {"registration", "login", "form_submission"}:
                            if any(a.source != "browser" for a in refinement.assertions):
                                reason = "Auth refinement rejected: process readiness is not an auth result; use browser post-submission assertions"
                                fingerprint = hashlib.sha256(decision.model_dump_json().encode()).hexdigest()
                                if rejected.get(fingerprint) == resource_identity():
                                    raise InterruptedError("No progress: identical invalid auth refinement repeated")
                                rejected[fingerprint] = resource_identity()
                                store.append(node_id=check.id, goal_id=check.id, source_tool="explorer", obs_type="agent_failure",
                                             payload={"ok": False, "reason": reason})
                                bus.emit(events.ToolRejected, {"tool": "refine", "node_id": check.id, "reason": reason})
                                save(last_event=reason)
                                continue
                            from wizard_kernel.contracts.verification import Assertion
                            before_submission = []
                            for previous in store.all():
                                if previous.goal_id != check.id:
                                    continue
                                if previous.source_tool == "browser_click" and previous.success and (previous.payload.get("data") or {}).get("submitted_form"):
                                    break
                                before_submission.append(previous)
                            preview = check.model_copy(update={"assertions": [
                                Assertion.model_validate({**a.model_dump(), "after_submission": False})
                                for a in refinement.assertions if a.source == "browser"]})
                            if checks.verdict(checks.evaluate(preview, before_submission)) == "passed":
                                reason = "Auth result criteria already hold on the unsubmitted page; specify a real post-submission state change"
                                fingerprint = hashlib.sha256(decision.model_dump_json().encode()).hexdigest()
                                if rejected.get(fingerprint) == resource_identity():
                                    raise InterruptedError("No progress: identical invalid auth criteria repeated")
                                rejected[fingerprint] = resource_identity()
                                store.append(node_id=check.id, goal_id=check.id, source_tool="explorer", obs_type="agent_failure",
                                             payload={"ok": False, "reason": reason})
                                save(last_event=reason)
                                continue
                            for assertion in refinement.assertions:
                                if assertion.source == "browser":
                                    assertion.root.after_submission = True
                        if set(check.capabilities) == {'repository'}:
                            state.setdefault('repository_findings', {})[check.id] = {
                                'summary': flow_trace.safe_text(decision.reason, limit=2500),
                                'observation_ids': refinement.observation_ids}
                        check.assertions = refinement.assertions
                        check.unresolved_reason = ""
                        next(c for c in state["checks"] if c["id"] == check.id).update(check.model_dump())
                        save()
                        continue
                    if decision.refinement is not None:
                        raise ValueError("Only a refine decision can contain new expectations")
                    if decision.kind != "tool":
                        if decision.action is not None:
                            raise ValueError("Non-tool decision cannot contain an action")
                        if decision.kind == "evaluate" and browser and browser.started:
                            for assertion in check.assertions:
                                if assertion.source != "browser":
                                    continue
                                submitted = any(o.goal_id == check.id and o.source_tool == "browser_click"
                                                and o.success and (o.payload.get("data") or {}).get("submitted_form") for o in store.all())
                                if assertion.after_submission and not submitted:
                                    continue
                                if assertion.field in {"visible", "enabled", "count"}:
                                    checked = validator.validate(ToolRequest(tool="browser_snapshot", parameters={}), inv.budget_remaining)
                                    if checked.valid:
                                        execute("browser_snapshot", {}, checked.sanitised_params, check.id, purpose="assertion")
                                    continue
                                params = {k: getattr(assertion, k) for k in ("field", "operator", "expected")}
                                validated = validator.validate(ToolRequest(tool="browser_assertion", parameters=params), inv.budget_remaining)
                                if validated.valid:
                                    execute("browser_assertion", params, validated.sanitised_params, check.id, purpose="assertion")
                            results = checks.evaluate(check, store.all())
                        status = checks.verdict(results) if decision.kind == "evaluate" else "unverified"
                        state["results"][check.id] = {"status": status, "assertions": results,
                                                      "reason": flow_trace.safe_text("; ".join(r.get("reason") or "Predicate not satisfied" for r in results if r['verdict'] != 'passed') if decision.kind == 'evaluate' else decision.reason)}
                        save()
                        if status == "passed":
                            bus.emit(events.GoalSatisfied, {"goal_id": check.id, "goal_name": check.description})
                        if "browser" in check.capabilities or any(a.source == "browser" for a in check.assertions):
                            capture_screenshot(check.id)
                        break
                    if decision.action is None:
                        raise ValueError("Tool decision has no action")
                    tool = decision.action.tool
                    proposed = decision.action.parameters.model_dump()
                    params = copy.deepcopy(proposed)
                    if tool in {"browser_type", "browser_fill_form"}:
                        fields = params.get("fields", [params])
                        for field in fields:
                            reference = field.pop("value_ref")
                            if reference not in authorized:
                                raise InterruptedError("Required authorized form input is unavailable")
                            field["text"] = authorized[reference]
                    # An empty POST body is a real request; omit it for GET/HEAD.
                    if tool == "http_request" and params.get("method") != "POST":
                        params.pop("body", None)
                    action_id = hashlib.sha256(json.dumps([tool, proposed], sort_keys=True).encode()).hexdigest()
                    if rejected.get(action_id) == resource_identity() and not validator.retry_eligible(tool, params):
                        raise InterruptedError("No progress: identical rejected or failed action repeated")
                    if tool in {"browser_click", "browser_type", "browser_fill_form"}:
                        page = _resources(store.all()).get("browser") or {}
                        selectors = {c.get("selector") for c in page.get("controls", [])}
                        requested = [f["selector"] for f in params["fields"]] if tool == "browser_fill_form" else [params["selector"]]
                        if any(selector not in selectors for selector in requested):
                            rejected[action_id] = resource_identity()
                            store.append(node_id=check.id, goal_id=check.id, source_tool="explorer", obs_type="agent_failure",
                                         payload={"ok": False, "tool": tool, "reason": "Selector is not present in current observed browser controls; refresh the snapshot"})
                            save()
                            continue
                        reason = _form_submission_rejection(check, page, params["selector"]) if tool == "browser_click" else None
                        if reason:
                            rejected[action_id] = resource_identity()
                            store.append(node_id=check.id, goal_id=check.id, source_tool="explorer", obs_type="agent_failure",
                                         payload={"ok": False, "tool": tool, "reason": reason})
                            bus.emit(events.ToolRejected, {"tool": tool, "node_id": check.id, "reason": reason})
                            save(last_event=reason)
                            continue
                    request_action = ToolRequest(tool=tool, parameters=params)
                    dependencies = (state.get("recovery_round") or {}).get("dependencies", {}).get(check.id, [])
                    if tool == "execute_command" and dependencies and all(state["results"].get(dep, {}).get("status") == "passed" for dep in dependencies):
                        previous_failure = any(e["check_id"] == check.id and e["tool"] == tool and e.get("success") is False
                                               and e["parameters"] == flow_trace.safe_parameters(proposed) for e in state["executions"])
                        proof_ids = {r["observation_id"] for dep in dependencies for r in state["results"][dep].get("assertions", [])
                                     if r.get("verdict") == "passed" and r.get("observation_id") and store.get(r["observation_id"]) is not None
                                     and store.get(r["observation_id"]).success}
                        if previous_failure and validator.authorize_recheck(request_action, proof_ids):
                            state.setdefault("recovery_rechecks", []).append({"check_id": check.id, "tool": tool, "proof_ids": sorted(proof_ids)})
                    validation = validator.validate(request_action, inv.budget_remaining)
                    if validation.valid and validation.observation_id:
                        if any(e['check_id'] == check.id for e in state.get('evidence_reuse', [])):
                            state['results'][check.id] = {'status': 'unverified', 'assertions': checks.evaluate(check, store.all()), 'reason': 'Repeated cached evidence adds no new facts; choose another source'}
                            save()
                            break
                        state.setdefault('evidence_reuse', []).append({'check_id': check.id, 'observation_id': validation.observation_id, 'tool': tool})
                        store.append(node_id=check.id, goal_id=check.id, source_tool='explorer', obs_type='agent_failure',
                            payload={'ok': False, 'reason': 'This read is already available. Reuse its observation ID or choose a different source.', 'observation_id': validation.observation_id})
                        save()
                        continue
                    if not validation.valid:
                        rejected[action_id] = resource_identity()
                        store.append(node_id=check.id, goal_id=check.id, source_tool="explorer", obs_type="agent_failure",
                                     payload={"ok": False, "tool": tool, "reason": validation.reason})
                        bus.emit(events.ToolRejected, {"tool": tool, "node_id": check.id, "reason": validation.reason})
                        save(last_event=validation.reason)
                        continue
                    if tool == "browser_screenshot":
                        if state.get("screenshot_attempts", 0) >= inv.options.get("max_screenshots", 4):
                            raise InterruptedError("Screenshot artifact budget exhausted")
                        state["screenshot_attempts"] = state.get("screenshot_attempts", 0) + 1
                    obs = execute(tool, proposed, validation.sanitised_params, check.id)
                    if not obs.success:
                        rejected[action_id] = resource_identity()
                    latest = checks.evaluate(check, store.all())
                    state["results"][check.id] = {"status": "pending", "assertions": latest}
                    if checks.verdict(latest) == "passed":
                        state["results"][check.id]["status"] = "passed"
                        save()
                        bus.emit(events.GoalSatisfied, {"goal_id": check.id, "goal_name": check.description})
                        if "browser" in check.capabilities or any(a.source == "browser" for a in check.assertions):
                            capture_screenshot(check.id)
                        break
                    save()
                    agent_executions = [e for e in state["executions"] if e.get("purpose") == "agent"]
                    if len(agent_executions) > 1 and agent_executions[-2].get("result_fingerprint") == agent_executions[-1]["result_fingerprint"] and not (
                            tool in {"read_file", "search_files", "path_exists"} and agent_executions[-2].get("parameters") != agent_executions[-1].get("parameters")):
                        if obs.success and tool in {'browser_snapshot', 'browser_extract'}:
                            stalled_page = _state_identity(_resources(store.all())['browser'])
                            reason = 'BROWSER_READ_UNCHANGED: repeated reads returned the same page; choose a different action from the observed state'
                            store.append(node_id=check.id, goal_id=check.id, source_tool='explorer', obs_type='agent_failure',
                                         payload={'ok': False, 'tool': tool, 'reason': reason})
                            state.setdefault('browser_read_recoveries', []).append({'check_id': check.id, 'observation_id': obs.id})
                            bus.emit(events.ToolRejected, {'tool': tool, 'node_id': check.id, 'reason': reason})
                            save(last_event=reason)
                            continue
                        raise InterruptedError("No progress: repeated execution produced no new result")
                else:
                    raise InterruptedError("Tool execution budget exhausted")
            required_ids = {c.id for c in spec.checks}
            state["required_check_ids"] = sorted(required_ids)
            pending = list(ordered)
            while True:
                while pending:
                    from wizard_kernel.control.recovery import next_ready
                    check = next_ready(pending, state["results"]) or pending[0]
                    pending.remove(check)
                    try:
                        run_check(check)
                    except InterruptedError as exc:
                        if not inv.options.get("enable_recovery") or not str(exc).startswith("No progress:"):
                            raise
                        state["results"][check.id] = {"status": "unverified", "reason": flow_trace.safe_text(str(exc))}
                        save()
                # Architecture completion requires coverage and synthesis, independent
                # of tactical checks such as existence. Every finding has content proof.
                if inv.intent == 'investigate' and 'architecture' in inv.targets and not state.get('architecture_coverage_ids') and state['results'] and all(
                        state['results'].get(c['id'], {}).get('status') == 'passed' or not c['assertions']
                        for c in state['checks']):
                    from wizard_kernel.contracts.verification import CheckSpec, architecture_report_model
                    repository_evidence = architecture_evidence()
                    repository_paths, path_chars = [], 0
                    for path in dict.fromkeys(selected + sorted(known_paths)):
                        if path_chars + len(path) > 7000:
                            break
                        repository_paths.append(path.replace('\\', '/'))
                        path_chars += len(path)
                    synthesis_context = {'original_request': _effective_request(inv),
                        'command_family': inv.intent, 'targets': inv.targets,
                        'architecture_synthesis': True, 'repository_evidence': repository_evidence,
                        'repository_paths': repository_paths,
                        'diagram_instruction': 'Populate evidence-backed subsystems with functional responsibilities and exact inspected file_paths. Assign components to these subsystems. Do not use an empty subsystem list when source files were inspected. Put short supported behavioral action labels on connections. Also populate components and connections for a compact application architecture diagram. Components are real application subsystems, entry points, services, models, or databases, never investigation tasks. Use repository-relative paths, concise labels and types, and observation_ids from supplied repository_evidence for each component and connection. Connections must explain a supported application dependency or call, never mere shared directory membership. Omit unsupported components and connections. Use unique simple IDs and valid component endpoints. Do not include secrets or absolute local paths in any descriptions.',
                        'instruction': 'Synthesize all six architecture areas from supplied evidence. Explain actual entry files and startup flow, client/server component boundaries (not account isolation), workspace packages, directories and configuration relationships. Each statement must follow from cited content. Use short exact verbatim substrings as targeted content predicates, preserving JSON whitespace and escapes; use separate predicates for separate terms. Do not reformat JSON or treat a database healthcheck as application startup. File existence alone is insufficient. For missing evidence use empty assertions and an exact blocker; do not invent facts.'}
                    proof_correction_used = False
                    for attempt in range(3):
                        synthesis = request('explorer', synthesis_context,
                                            architecture_report_model(synthesis_context['repository_evidence'],
                                                require_subsystems=any(source_path(r['path']) for r in synthesis_context['repository_evidence'])))
                        if attempt == 0 and synthesis.evidence_requests:
                            followed_up = False
                            for path in dict.fromkeys(synthesis.evidence_requests):
                                path = path.replace('\\', '/')
                                if path not in known_paths or inv.budget_remaining <= 0:
                                    continue
                                params = {'path': path, 'max_bytes': 8000}
                                checked = validator.validate(ToolRequest(tool='read_file', parameters=params), inv.budget_remaining)
                                if not checked.valid:
                                    continue
                                obs = execute('read_file', params, checked.sanitised_params,
                                              'architecture_coverage', purpose='architecture_evidence_followup')
                                state.setdefault('architecture_evidence_followup', []).append(
                                    {'path': path, 'observation_id': obs.id, 'success': obs.success})
                                followed_up = True
                            if followed_up:
                                synthesis_context['repository_evidence'] = architecture_evidence()
                                synthesis_context['evidence_followup'] = 'Use the new file observations to resolve earlier blockers. No further follow-up reads are available; cite actual content or retain the blocker.'
                                continue
                        evaluated_findings = []
                        for finding in synthesis.findings:
                            coverage_id = 'architecture_' + finding.area
                            while any(c['id'] == coverage_id for c in state['checks']):
                                coverage_id += '_coverage'
                            coverage = CheckSpec(id=coverage_id, description=finding.area + ': ' + finding.summary,
                                assertions=finding.assertions, unresolved_reason=finding.blocker, capabilities=['repository'])
                            evaluated_findings.append((coverage, checks.evaluate(coverage, store.all())))
                        if proof_correction_used or not any(checks.verdict(r) == 'failed' for _, r in evaluated_findings):
                            break
                        proof_correction_used = True
                        fs_store.write(inv.id, 'architecture_proposed_report.json', synthesis.model_dump())
                        feedback = []
                        evidence_by_id = {r['observation_id']: r for r in synthesis_context['repository_evidence']}
                        evidence_by_path = {r['path'].replace('\\', '/'): r for r in synthesis_context['repository_evidence']}
                        for c, rows in evaluated_findings:
                            details = []
                            for a in rows:
                                actual = str(a.get('actual') or '')
                                tokens = list(dict.fromkeys(re.findall(r'[\w.-]{2,80}', str(a['assertion'].get('expected', '')))))[:12]
                                sensitive = a['assertion'].get('case_sensitive', True)
                                present = [t for t in tokens if (t if sensitive else t.casefold()) in
                                           (actual if sensitive else actual.casefold())]
                                target = a['assertion'].get('target', '')
                                source = evidence_by_id.get(target) or evidence_by_path.get(target.replace('\\', '/')) or {}
                                expected = str(a['assertion'].get('expected', ''))
                                path = source.get('path', '').replace('\\', '/')
                                path_mistaken_for_content = (a['verdict'] == 'failed' and expected
                                    and expected in {path, path.rsplit('/', 1)[-1]})
                                details.append({**a, 'actual': actual[:1200] if a['verdict'] != 'passed' and a.get('actual') is not None else None,
                                    'actual_excerpt_truncated': a['verdict'] != 'passed' and len(actual) > 1200,
                                    'source_path': path, 'present_literal_tokens': present,
                                    'correction': ('FILE_IDENTITY_IS_NOT_CONTENT: the expected value names this file, '
                                        'but is absent from its content. Select a verbatim implementation excerpt that '
                                        'supports the finding, or report a blocker. Do not repeat this predicate.'
                                        if path_mistaken_for_content else
                                        'Use the cited observed content to correct this predicate; do not weaken the finding.'
                                        if a['verdict'] != 'passed' else 'Keep this passing predicate unchanged.')})
                            feedback.append({'area': c.id, 'results': details})
                        synthesis_context['evaluation_feedback'] = feedback
                        synthesis_context['recovery_instruction'] = 'One bounded correction is allowed for your synthesized predicates. A formatting mismatch does not mean the file or JSON fields are absent. Present literal tokens are diagnostics, not proof. Consult the supplied actual contents; for JSON use separate short exact predicates for keys and values instead of reformatted arrays. Preserve the architectural relation in the explanation and proof; do not weaken user requirements. If evidence does not support the finding, report its blocker.'
                    inspected = {r['path'] for r in architecture_evidence()}
                    coverage = state['architecture_coverage']
                    coverage['inspected_files'] = sorted(inspected)
                    coverage['uninspected_files'] = [p for p in candidates(known_paths) if p not in inspected]
                    coverage['unrepresented_boundaries'] = sorted({boundary(p)[1] for p in candidates(known_paths)} -
                                                                 {boundary(p)[1] for p in inspected})
                    state['architecture_findings'] = synthesis.model_dump()['findings']
                    state['architecture_diagram'] = {
                        'components': synthesis.model_dump()['components'],
                        'connections': synthesis.model_dump()['connections'],
                        'subsystems': synthesis.model_dump()['subsystems'],
                    }
                    state['architecture_coverage_ids'] = {f.area: c.id for f, (c, _) in zip(synthesis.findings, evaluated_findings)}
                    for coverage, evaluated in evaluated_findings:
                        state['checks'].append(coverage.model_dump())
                        graph.add(InvestigationNode(id='check_' + coverage.id, type='checkpoint', goal_id=coverage.id,
                            action={'description': coverage.description, 'assertions': [a.model_dump() for a in coverage.assertions]},
                            hypothesis=Hypothesis(kind=HypothesisKind.manual_escalate)))
                        state['results'][coverage.id] = {'status': checks.verdict(evaluated), 'assertions': evaluated,
                                                       'reason': coverage.unresolved_reason}
                    # Resolve unspecified architecture goals from the measured
                    # coverage predicates, never from a tool-rejection count.
                    if all(checks.verdict(r) == 'passed' for _, r in evaluated_findings):
                        proof = [a for c, _ in evaluated_findings for a in c.model_dump()['assertions']]
                        for c in state['checks']:
                            if not c['assertions']:
                                c.update(assertions=proof, unresolved_reason='')
                                resolved = checks.evaluate(CheckSpec.model_validate(c), store.all())
                                state['results'][c['id']] = {'status': checks.verdict(resolved), 'assertions': resolved}
                    save()
                # One review after meaningful work, never after every file read.
                # Review cannot manufacture evidence or overwrite goal predicates.
                if inv.intent == "verify" and getattr(policy, "requires_verifier", False) and any(
                        o.success and o.source_tool not in {"read_file", "list_tree", "path_exists", "search_files", "explorer"}
                        for o in store.all()):
                    from wizard_kernel.contracts.agent import VerifierAssessment
                    save(state=LifecycleState.reporting, last_event="Reviewing execution evidence")
                    proof_ids = {a.get("observation_id") for result in state["results"].values() for a in result.get("assertions", [])}
                    proof_ids.update(o.id for o in store.all() if o.source_tool == "browser_click" and o.success
                                     and (o.payload.get("data") or {}).get("submitted_form"))
                    proof_ids.update(o.id for o in store.all() if o.success and o.source_tool in {
                        "browser_fill_form", "browser_type", "browser_snapshot", "browser_extract"})
                    review_evidence = []
                    for o in store.all():
                        if o.id not in proof_ids:
                            continue
                        data = o.payload.get("data") or {}
                        page = data.get("page_observation") or data
                        detail = {key: page[key] for key in ("url", "title", "text", "snapshot", "is_running", "active", "status_code", "body_preview", "exit_code") if key in page}
                        if o.source_tool == "browser_fill_form":
                            detail = {"all_filled": data.get("all_filled"), "fields": [
                                {"selector": f.get("selector"), "typed": f.get("typed")} for f in data.get("fields", [])]}
                        if not detail:
                            detail = {key: o.payload[key] for key in ("exit_code", "stdout", "error") if key in o.payload}
                        review_evidence.append({"id": o.id, "goal_id": o.goal_id, "tool": o.source_tool, "success": o.success,
                            "submitted_form": bool(data.get("submitted_form")),
                            "result": flow_trace.safe_text(json.dumps(_redact(detail, authorized, public_refs), default=str), limit=1800)})
                    review_identity = hashlib.sha256(json.dumps({"results": {k: v for k, v in state["results"].items() if k in required_ids},
                        "evidence": [e for e in review_evidence if e["tool"] not in {"read_file", "path_exists", "browser_screenshot"}]}, sort_keys=True).encode()).hexdigest()
                    if state.get("review_fingerprint") != review_identity:
                        state["review_fingerprint"] = review_identity
                        assessment = request("verifier", {"investigation_id": inv.id, "request": _effective_request(inv),
                            "checks": state["checks"], "results": state["results"],
                            "evidence": review_evidence[-16:]}, VerifierAssessment)
                        if assessment.investigation_id != inv.id:
                            raise ValueError("Verifier assessment belongs to another investigation")
                        state["verifier"] = assessment.model_dump()
                        if assessment.assessment != "needs_more_work":
                            state["stop_reason"] = ""
                        if assessment.assessment == "needs_more_work":
                            details = assessment.recommended_additional_investigations or assessment.weak_claims
                            state["stop_reason"] = flow_trace.safe_text("Verifier review needs more evidence: " + "; ".join(details), limit=1800)
                    save()
                missing = [c.id for c in spec.checks if c.id in required_ids and state["results"].get(c.id, {}).get("status") != "passed"]
                review_missing = state.get("verifier", {}).get("assessment") == "needs_more_work"
                eligible = {c.id for c in spec.checks if c.id in (missing or required_ids)
                            and (can_browser or "browser" not in set(c.capabilities) | {a.source for a in c.assertions})
                            and (can_execute or not (set(c.capabilities) | {a.source for a in c.assertions}) - {"repository"})}
                if (not inv.options.get("enable_recovery") or state.get("recovery_attempted") or
                        not (missing or review_missing) or not eligible or not store.count() or len(spec.checks) >= 8 or inv.budget_remaining < 2 or
                        state["model_calls"] >= max_calls - 1):
                    break
                guard()
                from wizard_kernel.contracts.verification import RecoveryPlan
                from wizard_kernel.control.recovery import admit
                state["recovery_attempted"] = True
                save(last_event="Planning one bounded recovery round")
                capabilities = {"repository"} | ({"process", "command", "http"} if can_execute else set()) | ({"browser"} if can_browser else set())
                plan = request("planner", {"recovery_request": True, "original_request": flow_trace.safe_text(_redact(_effective_request(inv), authorized, public_refs)),
                    "checks": state["checks"], "results": state["results"],
                    "missing_check_ids": sorted(eligible),
                    "available_capabilities": sorted(capabilities), "helper_slots": min(3, 8-len(spec.checks)),
                    "review": state.get("verifier"), "discovery": _redact(discovery, authorized, public_refs),
                    "recent_observations": [{"id": o.id, "goal_id": o.goal_id, "tool": o.source_tool,
                        "success": o.success, "result": flow_trace.safe_text(json.dumps(_redact(o.payload, authorized, public_refs)), limit=1800)}
                        for o in store.all()[-4:]], "remaining_tool_budget": inv.budget_remaining}, RecoveryPlan)
                try:
                    spec, helpers, dependencies = admit(spec, plan, state["results"], store.all(), capabilities=capabilities, eligible_ids=eligible)
                except ValueError as exc:
                    state["recovery_rejected"] = flow_trace.safe_text(str(exc))
                    state["stop_reason"] = "Recovery delta rejected: " + state["recovery_rejected"]
                    save(last_event="Recovery delta rejected")
                    break
                if not helpers:
                    state["recovery_declined"] = plan.reason
                    state["stop_reason"] = state["stop_reason"] or "No safe recovery: " + flow_trace.safe_text(plan.reason)
                    save()
                    break
                state["recovery_round"] = {"reason": plan.reason, "dependencies": dependencies,
                                           "observation_ids": plan.observation_ids, "helper_ids": [c.id for c in helpers]}
                state["checks"] = spec.model_dump()["checks"]
                for c in spec.checks:
                    old = graph.get("check_" + c.id)
                    if old:
                        graph.add(old.model_copy(update={"depends_on": ["check_" + d for d in c.depends_on]}))
                    else:
                        graph.add(InvestigationNode(id="check_" + c.id, type="checkpoint", goal_id=c.id,
                            parent_id="check_" + next(goal for goal, children in dependencies.items() if c.id in children),
                            depends_on=["check_" + d for d in c.depends_on], action={"description": c.description},
                            hypothesis=Hypothesis(kind=HypothesisKind.manual_escalate)))
                for goal_id in dependencies:
                    state.setdefault("result_history", {}).setdefault(goal_id, []).append(state["results"].pop(goal_id, {}))
                pending = helpers + [c for c in spec.checks if c.id in dependencies or c.id in missing]
                # A second review is allowed only after new proof, under the same budgets.
                save(state=LifecycleState.investigation_loop, last_event="Recovery work admitted")

    except Exception as exc:
        state["provider_requests"] = getattr(policy, "provider_requests", 0)
        state["provider_metadata"] = getattr(policy, "last_metadata", {})
        state["stop_reason"] = flow_trace.safe_text(_redact(str(exc), authorized, public_refs))
        state["failure_kind"] = getattr(exc, "kind", "interrupted" if isinstance(exc, InterruptedError) else "runtime")
        state["provider_status"] = getattr(exc, "status", None)
        state["provider_request_id"] = getattr(exc, "request_id", None)
        if state.get("last_agent") == "verifier":
            state["verifier_failure"] = {"kind": state["failure_kind"], "detail": state["stop_reason"],
                                         "status": state["provider_status"]}
        flow_trace.record(inv.id, "runtime.failure", kind=state["failure_kind"], detail=state["stop_reason"],
                          status=state["provider_status"], request_id=state["provider_request_id"])
    finally:
        cleanup_errors = []
        for close in (sandbox.stop, browser.stop if browser else lambda: None):
            try:
                close()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        browsers.unregister_runtime(inv.id)
        state["cleanup"] = "Completed" if not cleanup_errors else "Failed: " + ", ".join(cleanup_errors)
        for check in state["checks"]:
            result = state["results"].setdefault(check["id"], {})
            if result.get("status") not in {"passed", "failed", "evaluation_error"}:
                result.update(status="unverified", reason=state["stop_reason"] or result.get("reason") or "Not evaluated")
        required_ids = set(state.get("required_check_ids", state["results"]))
        required_ids.update(state.get('architecture_coverage_ids', {}).values())
        statuses = [state["results"].get(key, {}).get("status") for key in required_ids]
        final = LifecycleState.completed if statuses and all(s == "passed" for s in statuses) else LifecycleState.incomplete
        if inv.intent == 'investigate' and 'architecture' in inv.targets and not state.get('architecture_coverage_ids'):
            # Passing preparation checks cannot substitute for the required
            # architecture synthesis, including provider/context failures.
            final = LifecycleState.incomplete
        if state.get("verifier_failure") or state.get("verifier", {}).get("assessment") == "needs_more_work":
            final = LifecycleState.incomplete
        if inv.intent == "report" and state.get("report_source"):
            final = LifecycleState.completed
        if "failed" in statuses or "evaluation_error" in statuses or state.get("failure_kind") in {"runtime", "configuration", "schema", "provider_shape"} or cleanup_errors:
            final = LifecycleState.failed
        if inv.cancel_requested or inv.state == LifecycleState.cancelled:
            final = LifecycleState.cancelled
        if final not in {LifecycleState.completed, LifecycleState.cancelled} and not state["stop_reason"]:
            unresolved = [(key, state["results"].get(key, {})) for key in sorted(required_ids)
                          if state["results"].get(key, {}).get("status") != "passed"]
            if unresolved:
                key, result = next(((k, r) for k, r in unresolved
                    if r.get("status") in {"failed", "evaluation_error"}), unresolved[0])
                reason = next((row.get("reason") for row in result.get("assertions", [])
                               if row.get("verdict") != "passed" and row.get("reason")), None)
                state["stop_reason"] = flow_trace.safe_text(
                    f"{key}: {reason or result.get('reason') or 'Required evidence remains missing'}")
        try:
            final = save(state=final, last_event=state["stop_reason"] or "Verification checks evaluated")
        except OSError as exc:
            manager.update(inv.id, state=LifecycleState.failed, error=type(exc).__name__, last_event="Investigation report could not be saved")
            return
        path = fs_store.report_path(inv.id)
        bus.emit(events.ReportGenerated, {"report_path": str(path), "status": final.value})
        if final != LifecycleState.completed:
            bus.emit(events.InvestigationIncomplete, {"reason": state["stop_reason"], "status": final.value})
