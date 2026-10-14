"""Main investigation loop — the only algorithm that matters.

Invariants (never violate):
1. Observations immutable after creation.
2. Claims enter only through EvidenceEngine.
3. Planner/Agents never write graphs or trust.
4. Tool failures → Observations, not crashes.
5. No technology-specific meaning in Kernel core.
6. Investigations never share state.
7. Budget always terminates.

Phase 6 Agent Integration:
- Explorer Agent receives node context, returns a ToolRequest.
- Runtime validates ToolRequest deterministically (no blind execution).
- Verifier Agent periodically reviews admitted claims (read-only assessment).
- Runtime independently decides whether to act on Verifier's recommendation.
- Agents NEVER set trust, write to graphs, or mark goals complete.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from wizard_kernel.belief import extractors
from wizard_kernel.belief.evidence import EvidenceEngine
from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.belief.trust import source_tier_for_tool
from wizard_kernel.contracts.node import InvestigationNode, Hypothesis, HypothesisKind
from wizard_kernel.contracts.plan import TechnologyPlan
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.context.engine import ContextEngine
from wizard_kernel.control import hypothesis as hyp_eval
from wizard_kernel.control import flow_trace
from wizard_kernel.control.goals import Goal, GoalEngine, evidence_categories_for_tool
from wizard_kernel.ports.goal_policy import goal_evidence_for
from wizard_kernel.control.investigation_graph import InvestigationGraph, register_graph
from wizard_kernel.control.priority import next_ready
from wizard_kernel.control.tool_validator import ToolRequestValidator, BROWSER_TOOLS
from wizard_kernel.reality.observations import ObservationStore
from wizard_kernel.session.budget import BudgetManager
from wizard_kernel.session import events as event_bus
from wizard_kernel.session.investigation import Investigation
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store
from wizard_kernel.world import repository, scanner
from wizard_kernel.world.sandbox import get_sandbox
from wizard_kernel.world.tools import ToolExecutor

if TYPE_CHECKING:
    from wizard_kernel.ports.planner import PlannerPort
    from wizard_kernel.ports.agents import ExplorerPort, VerifierPort

log = logging.getLogger(__name__)

_TOOL_TO_OBS_TYPE: dict[str, str] = {
    "read_file":       "file_content",
    "list_tree":       "filesystem",
    "execute_command": "command_result",
    "search_files":    "search_hits",
    "check_port":      "port_check",
    "path_exists":     "path_check",
    "start_process":   "command_result",
    "read_process":    "command_result",
    "browser_navigate": "browser_action",
    "browser_click":    "browser_action",
    "browser_type":     "browser_action",
    "browser_fill_form": "browser_action",
    "browser_back":     "browser_action",
    "browser_snapshot": "page_content",
    "browser_assertion": "page_content",
    "browser_extract":  "page_content",
    "http_request": "http_response",
}

# How many nodes complete before the Verifier Agent is consulted
_VERIFIER_INTERVAL = 5

# A served local endpoint printed by a dev server / app on startup. Deliberately
# generic — a URL to a loopback host, or a "listening/running on port N" line —
# never a framework- or sample-specific route. The port group is optional so a
# bare `http://localhost` still yields the scheme's default.
_SERVED_URL_RE = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?::(\d{2,5}))?\b", re.I
)
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_SERVED_PORT_RE = re.compile(
    r"(?:listening|running|started|serving|ready).{0,40}?\bport\s*[:=]?\s*(\d{2,5})", re.I
)


def _extract_endpoints(text: str) -> list[tuple[str, int]]:
    """All loopback endpoints a process actually announced in its output."""
    # Strip terminal colors before parsing: a sequence inserted between the
    # host colon and port otherwise makes `localhost:5173` look like port 80.
    text = _ANSI_ESCAPE_RE.sub("", text or "")
    endpoints: list[tuple[str, int]] = []
    for match in _SERVED_URL_RE.finditer(text):
        url = match.group(0).rstrip("/")
        port = int(match.group(1)) if match.group(1) else (443 if url.lower().startswith("https") else 80)
        if 1 <= port <= 65535 and (url, port) not in endpoints:
            endpoints.append((url, port))
    for match in _SERVED_PORT_RE.finditer(text):
        port = int(match.group(1))
        endpoint = (f"http://localhost:{port}", port)
        if 1 <= port <= 65535 and endpoint not in endpoints:
            endpoints.append(endpoint)
    return endpoints


def _extract_endpoint(text: str) -> "tuple[str | None, int | None]":
    """Compatibility view of the first endpoint found in process output."""
    endpoints = _extract_endpoints(text)
    return endpoints[0] if endpoints else (None, None)


def _start_declared_servers(tools, obs_store, repo_path, bus, probed) -> None:
    """Start every `long_running` command the repository declares, and probe it.

    The whole application, not one service: a sign-up flow fills a client form
    that POSTs to a backend, so both must be up before the browser submits or it
    lands in nothing. Discovered from the repo's own manifest
    (`_discover_runnable_commands`) — nothing here names a workspace, script,
    port or route. Each server is started once and its endpoint discovered +
    probed via the existing readiness path. Best-effort: a server that fails to
    start is recorded and the run continues.
    """
    from wizard_kernel.context.packager import _discover_runnable_commands
    try:
        commands = _discover_runnable_commands(repo_path)
    except Exception:  # noqa: BLE001 — discovery must never abort a run
        return
    for cmd in [c for c in commands if c.get("lifecycle") == "long_running"][:4]:
        command, cwd = cmd.get("command"), cmd.get("cwd") or "."
        key = f"bringup:{command}@{cwd}"
        if not command or key in probed:
            continue
        probed.add(key)
        payload = tools.execute({"tool": "start_process",
                                 "params": {"command": command, "cwd": cwd}})
        obs_store.append(
            node_id="runtime_server_bringup", source_tool="start_process",
            obs_type=_TOOL_TO_OBS_TYPE.get("start_process", "command_result"),
            payload=payload, goal_id=None, tool_request_id=None,
            execution_id=uuid.uuid4().hex,
            evidence_categories=evidence_categories_for_tool("start_process", payload),
        )
        if payload.get("ok"):
            node = InvestigationNode(
                id="runtime_server_bringup", type="execute", action={},
                hypothesis=Hypothesis(kind=HypothesisKind.always_success))
            try:
                _probe_started_process(tools, obs_store, node, None, payload)
            except Exception:  # noqa: BLE001 — probing is best-effort
                pass


def _probe_started_process(
    tools: "ToolExecutor",
    obs_store: ObservationStore,
    node: InvestigationNode,
    active_goal_id: "str | None",
    payload: dict,
    *,
    validator: ToolRequestValidator | None = None,
    timeout_seconds: float = 20.0,
    poll_interval: float = 0.25,
    attempts: int | None = None,
    delay: float | None = None,
    cancel_check=None,
    sanitize=None,
) -> "str | None":
    """Runtime-owned readiness + endpoint discovery after a server is started.

    `start_process` proves the process is *alive*, not that it is *ready* or that
    anything is listening — the gap that left a run reading files forever after
    `npm run dev` came up, because nothing turned a live process into a reachable
    endpoint for the browser to use. The Runtime does that here, deterministically
    (invariant 3: no LLM): read the process output, extract the URL/port the
    process itself printed, and probe it with bounded polling. Every step is
    appended as a real observation, so the discovered endpoint and its readiness
    land in the Explorer's `resource_state` — which is what lets the browser phase
    begin — and the evidence is provenanced, never guessed.

    Returns the reachable URL once a probe succeeds, else None. The deadline
    bounds startup waiting; readiness is established only by a successful
    `check_port`, never by elapsed time or process liveness. `attempts`/`delay`
    remain available for deterministic callers/tests.
    """
    handle = ((payload.get("meta") or {}).get("handle_id")
              or ((payload.get("data") or {}).get("handle_id")))
    if not handle:
        return None
    # A parent process may print its child-launch banner well before the child
    # server binds. Keep observing the same process until it announces an
    # endpoint and that endpoint actually accepts connections, or the bounded
    # startup deadline/process exit is reached. A one-shot five-second window
    # handed control back to Explorer with a live-but-unready process, where the
    # model repeatedly requested the already-running command.
    interval = max(0.0, delay if delay is not None else poll_interval)
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    max_reads = max(1, attempts) if attempts is not None else None
    endpoints: dict[int, str] = {}
    last_probe_at: dict[int, float] = {}
    last_process_signature = None
    reads = 0
    while reads == 0 or (max_reads is not None and reads < max_reads) or (
        max_reads is None and time.monotonic() < deadline
    ):
        if cancel_check:
            cancel_check()
        rp = tools.execute({"tool": "read_process", "params": {"handle_id": handle}})
        if sanitize:
            rp = sanitize(rp)
        reads += 1
        data = rp.get("data") or {}
        output = " ".join(str(data.get(k) or "") for k in
                           ("stdout_so_far", "stderr_so_far", "stdout", "stderr"))
        text = " ".join((output, str(data.get("command") or ""),
                         str(data.get("cwd") or "")))
        running = data.get("is_running", rp.get("is_running"))
        signature = (running, data.get("exit_code"), text)
        if signature != last_process_signature:
            obs_store.append(
                node_id=node.id, source_tool="read_process",
                obs_type=_TOOL_TO_OBS_TYPE.get("read_process", "command_result"),
                payload=rp, goal_id=active_goal_id, tool_request_id=None,
                execution_id=uuid.uuid4().hex,
                evidence_categories=evidence_categories_for_tool("read_process", rp),
            )
            last_process_signature = signature
        for url, port in _extract_endpoints(output):
            endpoints.setdefault(port, url)
        now = time.monotonic()
        ready_url = None
        for port, url in endpoints.items():
            if now - last_probe_at.get(port, 0.0) < 1.0:
                continue
            cp = tools.execute({"tool": "check_port", "params": {"port": port}})
            if sanitize:
                cp = sanitize(cp)
            cp.setdefault("meta", {})["handle_id"] = handle
            if validator is not None:
                # These Runtime-owned readiness probes use the same executor but
                # happen outside Explorer's ToolRequest path. Keep the validator's
                # prerequisite state in sync with the persisted real observation;
                # otherwise it rejects navigation despite a successful probe.
                validator.record_execution(
                    "check_port", {"host": "localhost", "port": port}, cp)
            last_probe_at[port] = now
            obs_store.append(
                node_id=node.id, source_tool="check_port",
                obs_type=_TOOL_TO_OBS_TYPE.get("check_port", "command_result"),
                payload=cp, goal_id=active_goal_id, tool_request_id=None,
                execution_id=uuid.uuid4().hex,
                evidence_categories=evidence_categories_for_tool("check_port", cp),
            )
            if (cp.get("data") or {}).get("active"):
                ready_url = ready_url or url
        if ready_url:
            return ready_url
        if running is False:
            break
        if max_reads is not None and reads >= max_reads:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if interval:
            time.sleep(min(interval, remaining))
    return None



def run(
    inv: Investigation,
    manager: InvestigationManager,
    planner: "PlannerPort",
) -> None:
    """Entry point. Sets up all sub-systems then delegates to _run_loop."""
    # Validate repository path before touching any sandbox (surfaces clean errors)
    try:
        repository.validate(inv.repository_path)
    except ValueError as exc:
        manager.update(inv.id, state=LifecycleState.failed,
                       last_event=f"invalid path: {exc}", error=str(exc))
        return

    bus = event_bus.create(inv.id)
    kg = KnowledgeGraph(inv.id)
    ev_engine = EvidenceEngine(kg)
    graph = InvestigationGraph(inv.id)
    # Publish the live graph so a watching surface can answer "what now / what
    # next" while the run is still going. persist() writes it to disk once, at the
    # end, which is far too late to watch anything by.
    register_graph(inv.id, graph)
    goals = GoalEngine(inv.id)
    obs_store = ObservationStore(inv.id)
    budget = BudgetManager(inv.budget_remaining)
    validator = ToolRequestValidator(
        inv.repository_path,
        allowed_domains=inv.options.get("allowed_domains", []),
        browser_enabled=bool(inv.options.get("browser_enabled")),
    )
    completed_ids: set[str] = set()

    # Context Engine: read-only projection of state into agent context (invariant 3).
    # Its token budget is the LLM context window (distinct from the tool-call
    # `budget` above); the window size is configurable per investigation.
    context_engine = ContextEngine(
        bus, max_context_tokens=inv.options.get("max_context_tokens", 8192)
    )

    sandbox_mode = inv.options.get("sandbox_mode", "local_dev")
    sandbox = get_sandbox(sandbox_mode)

    # Agentic browser — opt-in per investigation (invariant 6: one runtime, never
    # shared). get_browser does NOT import playwright; only browser.start() does,
    # so a missing dependency surfaces as a clean investigation failure below.
    browser = None
    if inv.options.get("browser_enabled"):
        from wizard_kernel.world import browser as browser_mod
        browser = browser_mod.get_browser(inv.options)
        # Register the investigation-scoped runtime for the browser viewer, but
        # defer Chromium startup until an accepted browser ToolRequest executes.
        browser_mod.register_runtime(inv.id, browser)

    from wizard_kernel.ports.agents import get_agents
    explorer, verifier = get_agents(inv.options)

    # Which implementation each seam actually got. The factories fall back to
    # mocks when a URL or an options key is missing, which is the right default
    # for tests but a silent one in a real run: an investigation wired to nothing
    # looks identical to one wired correctly until you read the reasoning strings.
    # Recording the choice as a first-class event makes the substitution visible
    # in the same trace as everything else.
    bus.emit(event_bus.SeamsResolved, {
        "planner": type(planner).__name__,
        "explorer": type(explorer).__name__,
        "verifier": type(verifier).__name__,
        "planner_url": inv.options.get("planner_url"),
        "agent_explorer_url": inv.options.get("agent_explorer_url"),
        "agent_verifier_url": inv.options.get("agent_verifier_url"),
    })
    flow_trace.record(inv.id, "runtime.seams", planner=type(planner).__name__,
                      explorer=type(explorer).__name__, verifier=type(verifier).__name__,
                      browser_enabled=bool(inv.options.get("browser_enabled")),
                      sandbox_mode=sandbox_mode)

    try:
        sandbox.start(inv.repository_path)
        tools = ToolExecutor(sandbox, inv.repository_path, browser=browser)
        _run_loop(inv, manager, planner, explorer, verifier, kg, ev_engine, graph, goals,
                  obs_store, tools, budget, bus, validator, completed_ids, context_engine)
    except Exception as exc:  # noqa: BLE001
        # A fatal Runtime error must still leave a report and a truthful terminal
        # state. _finalize is idempotent, so if _run_loop already finalized before
        # the raise, this call is a no-op; otherwise it generates the report from
        # whatever evidence survived and marks the run `failed` without masking exc.
        log.exception("investigation %s raised; finalizing as failed", inv.id)
        try:
            _finalize(inv, manager, graph, kg, goals, obs_store, bus, error=str(exc))
        except Exception:  # noqa: BLE001 — never let finalize's own failure hide the original
            log.exception("investigation %s: finalize failed after fatal error", inv.id)
            manager.update(inv.id, state=LifecycleState.failed,
                           last_event=f"fatal: {exc}", error=str(exc))
    finally:
        # The graph deliberately stays registered after the run ends: a viewer that
        # opens the live page once the investigation is already complete should see
        # its final shape, not an empty registry. This matches the manager, which
        # likewise keeps every investigation it has seen.
        sandbox.stop()
        if browser is not None:
            browser_mod.unregister_runtime(inv.id)
            browser.stop()


def _run_loop(
    inv: Investigation,
    manager: InvestigationManager,
    planner: "PlannerPort",
    explorer: "ExplorerPort",
    verifier: "VerifierPort",
    kg: KnowledgeGraph,
    ev_engine: EvidenceEngine,
    graph: InvestigationGraph,
    goals: GoalEngine,
    obs_store: ObservationStore,
    tools: ToolExecutor,
    budget: BudgetManager,
    bus: event_bus.EventBus,
    validator: ToolRequestValidator,
    completed_ids: set[str],
    context_engine: ContextEngine,
) -> None:
    # ── Scanning ──────────────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.scanning, last_event="fast scan started")
    flow_trace.record(inv.id, "runtime.lifecycle", state=LifecycleState.scanning.value)
    manifest = scanner.scan(inv.repository_path, inv.id)
    fs_store.write(inv.id, "manifest.json", manifest.model_dump())
    flow_trace.record(inv.id, "repository.scan.completed",
                      key_file_count=len(manifest.key_files),
                      key_files=[p for p in manifest.key_files[:60]
                                 if not str(p).lower().endswith(".env")],
                      manifest_fingerprint=flow_trace.fingerprint(manifest.model_dump(mode="json")))

    # ── Planning ──────────────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.planning, last_event="initial planner call")
    flow_trace.record(inv.id, "runtime.lifecycle", state=LifecycleState.planning.value)
    # inv.options is passed through because the planner is what decides whether to
    # plan a browser phase, and it can only do that if it is told a browser plane
    # exists (browser_enabled) and which hosts are reachable (allowed_domains).
    # inv.question rides along for the same reason: the planner plans what the
    # user asked, and `intent` — the command family — is not what they asked.
    # Passed by keyword, unlike the four before it, so an implementation still on
    # the old four-parameter signature fails with "got an unexpected keyword
    # argument 'question'" instead of a bare arity error that reads as a mystery.
    flow_trace.record(
        inv.id, "planner.initial.request",
        planner=type(planner).__name__, intent=inv.intent, question=inv.question,
        targets=inv.targets, repository_name=Path(inv.repository_path).name,
        manifest_key_file_count=len(manifest.key_files),
        browser_enabled=bool(inv.options.get("browser_enabled")),
    )
    planner_started = time.monotonic()
    try:
        plan = planner.initial(
            manifest, inv.intent, inv.targets, inv.options, question=inv.question
        )
    except Exception as exc:
        flow_trace.record(inv.id, "planner.initial.failure", planner=type(planner).__name__,
                          elapsed_ms=int((time.monotonic() - planner_started) * 1000),
                          error=flow_trace.safe_text(exc))
        raise
    fs_store.write(inv.id, "plan.json", plan.model_dump())
    flow_trace.record(inv.id, "planner.initial.response",
                      elapsed_ms=int((time.monotonic() - planner_started) * 1000),
                      **flow_trace.plan_summary(plan))

    # The Runtime strengthens Planner declarations with its deterministic policy;
    # a model cannot weaken a goal by omitting or under-declaring its evidence.
    for tech in plan.technologies:
        for goal_def in tech.initial_goals:
            policy = goal_evidence_for(goal_def.name)
            goals.add(Goal(
                id=f"goal_{uuid.uuid4().hex[:6]}",
                name=goal_def.name,
                required_claim_types=list(dict.fromkeys(
                    [*policy.required_claim_types, *goal_def.required_claim_types]
                )),
                required_evidence=list(dict.fromkeys(
                    [*policy.required_evidence, *goal_def.required_evidence]
                )),
                belief_threshold=goal_def.belief_threshold,
                requires_execution_evidence=(goal_def.requires_execution_evidence
                                             or policy.requires_execution_evidence),
            ))
    flow_trace.record(inv.id, "runtime.goal_contracts.applied",
                      goals=flow_trace.goal_states(goals, obs_store.all()))

    for node in plan.seed_nodes:
        graph.add(node)
    flow_trace.record(inv.id, "runtime.graph.seeded",
                      nodes=[flow_trace.node_summary(n) for n in plan.seed_nodes])

    manager.update(inv.id, state=LifecycleState.investigation_loop,
                   last_event="loop started", active_goals=goals.to_api_list(obs_store.all()))
    flow_trace.record(inv.id, "runtime.lifecycle", state=LifecycleState.investigation_loop.value)
    bus.emit(event_bus.InvestigationStarted, {"repository_path": inv.repository_path})

    nodes_since_last_verify = 0
    final_review_done = False
    # Why the loop stopped. Set only on the give-up path; the other two exits
    # are read off the budget and the goals when the loop is over.
    gave_up = False
    stop_reason: str | None = None

    # Deterministic convergence guards (Runtime-owned, no LLM). These are
    # distinct from the tool-call `budget`: that bounds *total* work, these bound
    # *unproductive* work so a stuck run ends in a handful of steps instead of
    # draining the whole budget one 12s-gated agent call at a time. Conservative
    # defaults, overridable per investigation.
    max_no_progress = int(inv.options.get("max_no_progress_steps", 6))
    max_consecutive_failures = int(inv.options.get("max_consecutive_failures", 4))
    max_replans_without_new_work = int(inv.options.get("max_replans_without_new_work", 3))
    no_progress_steps = 0
    consecutive_failures = 0
    replans_without_new_work = 0
    # start_process handles the Runtime has already run readiness discovery on,
    # so a node revisited does not re-probe the same server.
    _probed_handles: set[str] = set()
    # Nodes that FAILED (as opposed to merely completed). `completed_ids` holds
    # both — it only guards against re-running — so a separate set is what lets a
    # dependent of a failed node be cascade-failed instead of run on a
    # precondition that never happened.
    failed_ids: set[str] = set()


    # ── Core loop ─────────────────────────────────────────────────────────────
    while not budget.is_exhausted():
        # Check if cancelled externally
        if inv.state == LifecycleState.cancelled:
            log.info("investigation %s cancelled externally, halting loop.", inv.id)
            return

        # State committed by the previous iteration is now visible — drop cached
        # context so the Context Engine rebuilds against current state (§22).
        context_engine.on_state_mutation()

        # Build goal_urgency and trust maps for priority scoring
        goal_urgency = {
            g.id: 0.0 if g.state == "satisfied" else 1.0
            for g in goals.all()
        }
        kg_trust_by_goal = {
            g.id: kg.average_trust_for_types(g.required_claim_types)
            for g in goals.all()
        }

        node = next_ready(graph.all_nodes(), completed_ids,
                          goal_urgency=goal_urgency, kg_trust_by_goal=kg_trust_by_goal)

        if node is None:
            if goals.all_satisfied():
                break
            planner_context = _planner_next_context(
                inv, goals, kg, plan, budget, obs_store, "need_more_work",
                graph=graph, completed_ids=completed_ids)
            flow_trace.record(
                inv.id, "planner.next.request", planner=type(planner).__name__,
                context=flow_trace.planner_context_summary(planner_context),
                open_goals=[{"id": g.id, "name": g.name,
                             "missing": goals.evidence_status(g.id, obs_store.all())["missing"]}
                            for g in goals.open_goals()],
                existing_nodes=[flow_trace.node_summary(n) | {"state": n.state}
                                for n in graph.all_nodes()],
                observations=[{"id": o.id, "tool": o.source_tool,
                               "categories": o.evidence_categories, "success": o.success}
                              for o in obs_store.all()[-12:]],
            )
            planner_started = time.monotonic()
            try:
                new_nodes = planner.next_nodes(planner_context)
            except Exception as exc:
                flow_trace.record(inv.id, "planner.next.failure",
                                  elapsed_ms=int((time.monotonic() - planner_started) * 1000),
                                  error=flow_trace.safe_text(exc))
                raise
            flow_trace.record(inv.id, "planner.next.response",
                              elapsed_ms=int((time.monotonic() - planner_started) * 1000),
                              proposed_nodes=[flow_trace.node_summary(n) for n in new_nodes])
            if not new_nodes:
                # The Planner has no further steps to propose. That is the run
                # running out of ideas, not the run finishing — recorded so the
                # report can say which of the two happened.
                gave_up = True
                stop_reason = "Planner returned no additional nodes"
                flow_trace.record(inv.id, "runtime.no_progress", reason=stop_reason)
                break
            added_executable = False
            for n in new_nodes:
                if _already_scheduled(graph, completed_ids, n):
                    flow_trace.record(inv.id, "planner.node.deduplicated",
                                      proposed=flow_trace.node_summary(n),
                                      matching_candidates=[
                                          flow_trace.node_summary(existing) | {"state": existing.state}
                                          for existing in graph.all_nodes()
                                          if flow_trace.node_summary(existing).get("action_fingerprint")
                                          == flow_trace.node_summary(n).get("action_fingerprint")
                                      ],
                                      completed_node_count=len(completed_ids))
                    bus.emit(event_bus.PlannerNodeSkipped, {
                        "node_id": n.id, "type": n.type,
                        "reason": "a node for the same action is already queued",
                    })
                    continue
                graph.add(n)
                flow_trace.record(inv.id, "planner.node.accepted",
                                  node=flow_trace.node_summary(n))
                added_executable = True
            if added_executable:
                replans_without_new_work = 0
            else:
                # The Planner answered, but every node it proposed is already
                # scheduled or done. Nothing new to execute, no budget consumed —
                # left alone this spins forever re-asking for the same work. Count
                # it as a replan that made no progress and give up once the
                # Planner has proven it is only repeating itself.
                replans_without_new_work += 1
                if replans_without_new_work >= max_replans_without_new_work:
                    gave_up = True
                    stop_reason = ("the planner kept proposing work that was "
                                   "already scheduled")
                    flow_trace.record(inv.id, "runtime.no_progress",
                                      reason=stop_reason,
                                      repeated_replans=replans_without_new_work)
                    log.info("investigation %s halting: %s", inv.id, stop_reason)
                    break
            continue

        # Planner seed nodes are often intentionally goal-agnostic. Keep the
        # Runtime's context choice and evidence provenance aligned by assigning
        # their execution to the first still-open goal unless the Planner named
        # A node whose dependency FAILED must not run: its plan was written for a
        # state the failed step was supposed to produce. Browser form steps are
        # chained (fill → fill → submit), so running a later step after an earlier
        # one failed is exactly the stale-page execution the audit traced — the
        # submit landing on a page the fills never reached. Cascade the failure
        # instead of executing on a precondition that never happened.
        if failed_ids.intersection(getattr(node, "depends_on", []) or []):
            graph.mark_failed(node.id)
            completed_ids.add(node.id)
            failed_ids.add(node.id)
            bus.emit(event_bus.NodeFailed, {"node_id": node.id, "type": node.type,
                                            "reason": "DEPENDENCY_FAILED"})
            continue

        # one explicitly.
        active_goal_id = node.goal_id
        if active_goal_id is None and goals.open_goals():
            active_goal_id = goals.open_goals()[0].id
            # Seed nodes can be goal-agnostic, but once Runtime attributes one
            # to a goal that identity must survive in the graph. Previously the
            # observations used this ID while the Explorer packet still showed
            # goal_id=None, so action context and evidence ownership disagreed.
            graph.assign_goal(node.id, active_goal_id)
            node = graph.get(node.id)

        graph.set_state(node.id, "running")
        manager.update(inv.id, last_event=f"executing {node.id} ({node.type})")
        flow_trace.record(inv.id, "runtime.node.selected",
                          node=flow_trace.node_summary(node), goal_id=active_goal_id,
                          already_completed=node.id in completed_ids)

        # ── Decide HOW to execute this node ───────────────────────────────────
        # A planned node is a proposal, not an executable browser action.
        # Ask Explorer against the latest observation each time; otherwise a
        # queued form script can act on a page that has since navigated away.
        ctx = context_engine.build_context("explorer", inv, node, goals, kg, budget, obs_store)
        tool_action, decision_failure = _resolve_tool_action(
            node, explorer, ctx.packet, validator, budget, bus,
            observations=obs_store.all(),
        )

        # A deterministic validator rejection is actionable feedback, not a
        # provider failure. Persist it before one corrective Explorer decision
        # so the existing Context Engine can show the rejected tool and reason.
        # Provider/schema failures still stop immediately, and the one-pass
        # bound prevents an invalid action from creating an LLM retry loop.
        if (tool_action is None and decision_failure
                and decision_failure.get("error_type") == "TOOL_REQUEST_REJECTED"):
            obs_store.append(
                node_id=node.id,
                source_tool="explorer",
                obs_type="agent_failure",
                payload={"ok": False, **decision_failure,
                         "investigation_id": inv.id, "node_id": node.id},
                goal_id=active_goal_id,
                tool_request_id=decision_failure.get("tool_request_id"),
            )
            context_engine.on_state_mutation()
            ctx = context_engine.build_context("explorer", inv, node, goals, kg, budget, obs_store)
            tool_action, decision_failure = _resolve_tool_action(
                node, explorer, ctx.packet, validator, budget, bus,
                observations=obs_store.all(),
            )

        if tool_action is None:
            failure = decision_failure or {
                "error_type": "EXPLORER_DECISION_FAILED",
                "detail": "Explorer did not provide a valid ToolRequest",
            }
            obs = obs_store.append(
                node_id=node.id,
                source_tool="explorer",
                obs_type="agent_failure",
                payload={"ok": False, **failure,
                         "investigation_id": inv.id, "node_id": node.id},
                goal_id=active_goal_id,
                tool_request_id=failure.get("tool_request_id"),
            )
            graph.mark_failed(node.id, obs_ids=[obs.id])
            completed_ids.add(node.id)
            failed_ids.add(node.id)
            budget.consume()
            manager.update(inv.id, budget_remaining=budget.remaining,
                           nodes_completed=inv.nodes_completed + 1)
            bus.emit(event_bus.NodeFailed, {"node_id": node.id, "type": node.type,
                                            "reason": failure["error_type"]})
            if failure["error_type"].startswith("EXPLORER_"):
                gave_up = True
                break
            # A decision-stage failure (e.g. a validator TOOL_REQUEST_REJECTED,
            # typically a duplicate the Explorer keeps re-proposing) is still a
            # failure and still no progress — count it toward the convergence
            # guards here, not only in the post-execution path below. Without
            # this, repeated rejections drained the ENTIRE budget (28 duplicate
            # start_process/execute_command rejections ran a 100-node budget for
            # 9 minutes) because the guard never saw them. Now a stuck re-proposal
            # loop halts in a handful of steps and still finalizes with a report.
            consecutive_failures += 1
            no_progress_steps += 1
            if consecutive_failures >= max_consecutive_failures:
                gave_up = True
                stop_reason = (f"{consecutive_failures} consecutive rejected/failed "
                               f"decisions with no recovery")
                log.info("investigation %s halting: %s", inv.id, stop_reason)
                break
            if no_progress_steps >= max_no_progress:
                gave_up = True
                stop_reason = f"{no_progress_steps} steps produced no new evidence"
                log.info("investigation %s halting: %s", inv.id, stop_reason)
                break
            continue

        # The step is BEGINNING, said before it runs rather than after.
        #
        # Every other node event in this bus is retrospective: `node.completed`
        # and `node.failed` both arrive once the answer is already known. A
        # viewer watching a run therefore never saw it *do* anything — the trace
        # showed a plan being accepted, then a column of results, with the work
        # itself invisible between them. That is what a run looks like when it is
        # reading a script back to you rather than performing it.
        #
        # Emitted here, after the tool action is resolved and immediately before
        # `_safe_execute`, because that is the first moment the step is a concrete
        # action rather than an intention: the node's own `action` may be
        # `browser_click` while what actually runs is whatever the Explorer
        # decided, and announcing the node instead of the resolved tool would name
        # the wrong thing on exactly the steps a viewer most wants named.
        #
        # The tool and parameters here are the validated Explorer decision, so
        # the trace names the action that Runtime is about to execute.
        bus.emit(event_bus.NodeStarted, {
            "node_id": node.id,
            "type": node.type,
            "tool": tool_action.get("tool", "unknown"),
            "params": tool_action.get("params", {}) or {},
            "goal_id": active_goal_id,
        })

        # Execute — failures become observations, never crashes (invariant 4)
        execution_id = uuid.uuid4().hex
        flow_trace.record(inv.id, "runtime.execution.started", node_id=node.id,
                          goal_id=active_goal_id,
                          tool_request_id=tool_action.get("tool_request_id"),
                          execution_id=execution_id,
                          tool=tool_action.get("tool"),
                          parameters=flow_trace.safe_parameters(tool_action.get("params") or {}))
        execution_started = time.monotonic()
        payload = _safe_execute(tools, tool_action)
        # The validator's resource prerequisites advance only from the actual
        # executor result. A requested/planned action never marks a resource ready.
        validator.record_execution(
            tool_action.get("tool", ""), tool_action.get("params", {}) or {}, payload,
        )

        # Immutable observation (invariant 1)
        tool_name = tool_action.get("tool", "unknown")
        obs = obs_store.append(
            node_id=node.id,
            source_tool=tool_name,
            obs_type=_TOOL_TO_OBS_TYPE.get(tool_name, "command_result"),
            payload=payload,
            goal_id=active_goal_id,
            tool_request_id=tool_action.get("tool_request_id"),
            execution_id=execution_id,
            evidence_categories=evidence_categories_for_tool(tool_name, payload),
        )
        flow_trace.record(inv.id, "runtime.execution.finished", node_id=node.id,
                          goal_id=active_goal_id, observation_id=obs.id,
                          tool_request_id=tool_action.get("tool_request_id"), tool=tool_name,
                          execution_id=execution_id,
                          success=bool(payload.get("ok", True)),
                          elapsed_ms=int((time.monotonic() - execution_started) * 1000),
                          evidence_categories=obs.evidence_categories)

        # Narration plane: discrete browser.* events on the EventBus. Pixels stream
        # separately over the screencast WebSocket and never enter event history.
        if tool_name.startswith("browser_") and payload.get("ok"):
            _emit_browser_narration(bus, tool_name, payload.get("data", {}) or {},
                                    page=_current_page(tools))

        # A started server is a liveness signal, not a readiness one. The Runtime
        # follows it up itself — read the process output, discover the endpoint it
        # printed, probe it — so a reachable URL lands in context and the browser
        # phase can begin, rather than the run stalling because nothing turned a
        # running process into an endpoint. Once per handle; the extra read/probe
        # observations it files are what the Explorer then reasons over.
        process_not_ready = False
        if tool_name == "start_process" and payload.get("ok") and node.id not in _probed_handles:
            _probed_handles.add(node.id)
            ready_endpoint = _probe_started_process(
                tools, obs_store, node, active_goal_id, payload,
                validator=validator)
            flow_trace.record(
                inv.id, "runtime.process_readiness", node_id=node.id,
                goal_id=active_goal_id,
                state="ready" if ready_endpoint else "not_established",
                endpoint=ready_endpoint,
            )
            if not ready_endpoint:
                # Do not send another LLM decision while this process is still
                # running without a discovered/reachable endpoint. That caused
                # repeated identical start_process requests and burned provider
                # calls. Finish recording this actual execution first; then stop
                # with an honest incomplete state.
                process_not_ready = True
                stop_reason = (
                    "process started but no endpoint was announced and confirmed "
                    "reachable before the readiness deadline"
                )

        # ── Deterministic hypothesis evaluation (invariant 3 — no LLM needed) ─
        source_tier = source_tier_for_tool(tool_name)
        node_outcome = hyp_eval.evaluate(node, obs)
        # Whether the tool ACTUALLY succeeded, independent of the node's
        # hypothesis. An `always_success` node otherwise reports a failed
        # navigation/click/fill as `expected_success`, the node is marked
        # complete, and the queued follow-up steps run against a page that never
        # changed (or changed underneath them) — the stale-page execution the
        # audit traced. A tool that returned ok=False never completes its node, so
        # dependents do not proceed on it.
        action_ok = bool(payload.get("ok", True))
        planned_action_matches = _planned_action_matches(node.action, tool_name,
                                                          tool_action.get("params") or {})
        new_claims_this_node = 0

        match node_outcome:
            case "expected_success" if node.on_success and planned_action_matches and action_ok:
                result = ev_engine.admit(
                    inv_id=inv.id,
                    claim_type=node.on_success.claim_type,
                    key=node.on_success.key,
                    value=node.on_success.value,
                    obs_id=obs.id,
                    support_type="support",
                    source_tier=source_tier,
                    node_id=node.id,
                )
                if result:
                    new_claims_this_node += 1
                    bus.emit(event_bus.ClaimAdmitted, {
                        "claim_type": node.on_success.claim_type,
                        "key": node.on_success.key,
                        "value": node.on_success.value,
                    })
            case "expected_failure" if node.on_failure and planned_action_matches:
                result = ev_engine.admit(
                    inv_id=inv.id,
                    claim_type=node.on_failure.claim_type,
                    key=node.on_failure.key,
                    value=node.on_failure.value,
                    obs_id=obs.id,
                    support_type="contradict",
                    source_tier=source_tier,
                    node_id=node.id,
                )
                if result:
                    new_claims_this_node += 1
                    # A contradicting claim is admitted into the KG exactly like a
                    # supporting one — it shows up in the report's evidence index — so
                    # it must be narrated exactly like one too. Without this the
                    # negative controls are invisible on the bus: the graph contradicts
                    # itself and no viewer can see it happen.
                    bus.emit(event_bus.ClaimAdmitted, {
                        "claim_type": node.on_failure.claim_type,
                        "key": node.on_failure.key,
                        "value": node.on_failure.value,
                    })
            case "expected_success" | "expected_failure":
                # Explorer executed a different action than the Planner's
                # hypothesis describes. Keep the actual observation/extractors,
                # but never attach the planned claim template to it.
                pass
            case _:
                # Unexpected — escalate to Planner (invariant 3: Planner never writes KG)
                flow_trace.record(inv.id, "planner.interpret.request",
                                  node_id=node.id,
                                  observation=flow_trace.observation_summary(obs))
                interpreted = planner.interpret(node, obs)
                flow_trace.record(inv.id, "planner.interpret.response",
                                  node_id=node.id,
                                  proposed_nodes=[flow_trace.node_summary(n) for n in interpreted])
                for n in interpreted:
                    graph.add(n)

        # ── Run deterministic extractors on every observation ─────────────────
        for extract_result in extractors.extract(obs):
            result = ev_engine.admit(
                inv_id=inv.id,
                claim_type=extract_result.claim_type,
                key=extract_result.key,
                value=extract_result.value,
                obs_id=obs.id,
                support_type=extract_result.support_type,
                source_tier=source_tier,
                node_id=node.id,
            )
            if result:
                new_claims_this_node += 1
                bus.emit(event_bus.ClaimAdmitted, {
                    "claim_type": extract_result.claim_type,
                    "key": extract_result.key,
                    "value": extract_result.value,
                })

        # ── Update goals based on all new claims ──────────────────────────────
        satisfied_before = {g.id for g in goals.all() if g.state == "satisfied"}
        goals.evaluate_all(kg, obs_store.all())
        flow_trace.record(inv.id, "goal.evaluation",
                          goals=flow_trace.goal_states(goals, obs_store.all()))
        for g in goals.all():
            if g.state == "satisfied" and g.id not in satisfied_before:
                bus.emit(event_bus.GoalSatisfied, {"goal_id": g.id, "goal_name": g.name})

        # ── Complete or fail the node in the graph ────────────────────────────
        if node_outcome in ("expected_success", "expected_failure") and action_ok:
            graph.set_state(node.id, "complete", obs_ids=[obs.id])
            # A failure has always been narrated; a success has not, which left
            # the bus carrying only what went wrong. A viewer watching a run
            # that works saw nothing happen: no tool named, no command shown, no
            # result — the trace of a successful investigation was the trace of
            # an empty one. The payload carries the action and its outcome so a
            # reader can see which file was read and what a command returned,
            # rather than only that some node finished.
            bus.emit(event_bus.NodeCompleted, {
                "node_id": node.id,
                "type": node.type,
                "tool": tool_name,
                "params": tool_action.get("params") or {},
                "ok": bool(payload.get("ok", True)),
                "outcome": node_outcome,
            })
        else:
            graph.mark_failed(node.id, obs_ids=[obs.id])
            failed_ids.add(node.id)
            bus.emit(event_bus.NodeFailed, {"node_id": node.id, "type": node.type})

        completed_ids.add(node.id)
        budget.consume()
        nodes_since_last_verify += 1

        # ── Deterministic convergence accounting (no LLM) ─────────────────────
        # Progress = this step admitted new evidence. A node that merely
        # "completed" without producing a claim is not progress toward a goal.
        made_progress = new_claims_this_node > 0
        step_failed = not bool(payload.get("ok", True))
        if made_progress:
            no_progress_steps = 0
        else:
            no_progress_steps += 1
        if step_failed:
            consecutive_failures += 1
        else:
            consecutive_failures = 0

        manager.update(
            inv.id,
            budget_remaining=budget.remaining,
            nodes_completed=inv.nodes_completed + 1,
            claims_count=inv.claims_count + new_claims_this_node,
            active_goals=goals.to_api_list(obs_store.all()),
        )

        if process_not_ready:
            gave_up = True
            log.info("investigation %s halting: %s", inv.id, stop_reason)
            break

        if consecutive_failures >= max_consecutive_failures:
            gave_up = True
            stop_reason = (f"{consecutive_failures} consecutive tool/agent failures "
                           f"with no recovery")
            log.info("investigation %s halting: %s", inv.id, stop_reason)
            break
        if no_progress_steps >= max_no_progress:
            gave_up = True
            stop_reason = (f"{no_progress_steps} steps produced no new evidence")
            log.info("investigation %s halting: %s", inv.id, stop_reason)
            break

        if budget.is_low():
            bus.emit(event_bus.BudgetLow, {"remaining": budget.remaining, "total": budget.total})
            log.info("investigation %s budget low: %d/%d remaining",
                     inv.id, budget.remaining, budget.total)

        # Checkpoint nodes are explicitly placed by the Planner to mark goal satisfaction
        for ckpt in graph.checkpoint_nodes():
            if ckpt.id not in completed_ids:
                graph.set_state(ckpt.id, "complete")
                completed_ids.add(ckpt.id)
                if ckpt.goal_id:
                    goals.evaluate_checkpoint(ckpt.goal_id, kg, obs_store.all())

        # Two different judgements, and this used to be one test for both.
        #
        # "Every goal is satisfied" is the Runtime saying it has proved what the
        # plan asked for. "The plan is finished" is a statement about the graph,
        # and the graph is what holds the work. Conflating them ended runs in the
        # middle of their own plan: asked to log in and submit a sign-up form, the
        # run typed into the first field, that single INTERACTION claim closed
        # "Operate Web Surface", and the loop stopped with four steps of the
        # script it had just written still queued — a run reporting a success it
        # did not perform, on a form it left half-filled.
        #
        # A ready node is work the Planner placed whose turn has come. While one
        # remains, the run has planned something it has not done, and the honest
        # thing is to do it or to fail it. Nothing new is asked of the Planner on
        # this path — only nodes already in the graph run — so the extra work is
        # bounded by what was already planned, and the budget still terminates the
        # loop (invariant 7).
        if goals.all_satisfied() and not graph.get_ready_nodes(completed_ids):
            # Final review before declaring the investigation complete. The periodic
            # consultation below is interval-gated (every _VERIFIER_INTERVAL nodes),
            # so an investigation that closes its goals in fewer nodes than that
            # never reaches the Verifier at all — and the case the Verifier exists
            # for, goals that look satisfied on thin evidence, is exactly a short
            # investigation. Review once here so the Agent System's second half is
            # actually part of the flow.
            #
            # Not escalated: with every goal satisfied there is nothing to ask the
            # Planner for, and the Runtime's own judgement is that we are done. The
            # assessment is still recorded, so it is visible in the trace.
            if not final_review_done:
                final_review_done = True
                _consult_verifier(inv, verifier, kg, goals, graph, planner, plan,
                                  budget, obs_store, bus, completed_ids=completed_ids,
                                  escalate=False)
            break

        # ── Phase 6: Periodic Verifier Agent consultation ─────────────────────
        # The Verifier reviews claims but has NO authority to modify trust or goals.
        # The Runtime independently decides how to respond to its assessment.
        if nodes_since_last_verify >= _VERIFIER_INTERVAL:
            nodes_since_last_verify = 0
            _consult_verifier(inv, verifier, kg, goals, graph, planner, plan, budget,
                              obs_store, bus, completed_ids=completed_ids)

    if budget.is_exhausted():
        bus.emit(event_bus.BudgetExhausted, {"used": budget.used, "total": budget.total})

    _finalize(inv, manager, graph, kg, goals, obs_store, bus,
              gave_up=gave_up, stop_reason=stop_reason, budget=budget)


def _finalize(
    inv: Investigation,
    manager: InvestigationManager,
    graph: InvestigationGraph,
    kg: KnowledgeGraph,
    goals: GoalEngine,
    obs_store: ObservationStore,
    bus: event_bus.EventBus,
    *,
    gave_up: bool = False,
    stop_reason: str | None = None,
    budget: BudgetManager | None = None,
    error: str | None = None,
) -> None:
    """The single exit every run passes through — normal end OR fatal exception.

    Idempotent: a second call (e.g. the loop finished AND then run() unwinds, or
    two error paths race) must not write a second report or flip a settled
    terminal state. Guarded on a report already being on disk.

    `error` is set only by run()'s exception handler. Its presence forces the
    terminal state to `failed` (a Wizard malfunction, not an incomplete
    investigation) while still generating a report from whatever evidence was
    collected before the crash — so a run that dies mid-flight still leaves the
    developer the trace it had, and the original error is preserved in
    `last_event`/`error`, never masked by a cleanup problem.
    """
    # Cancellation is absorbing and owns its own messaging; never overwrite it.
    if inv.state == LifecycleState.cancelled:
        flow_trace.record(inv.id, "runtime.terminal", state="cancelled",
                          reason=inv.last_event, cleanup="runtime finally block")
        log.info("investigation %s was cancelled; not finalizing.", inv.id)
        return
    # Already finalized — a report exists. Do not duplicate work or events.
    try:
        if fs_store.read_text(inv.id, "verification_report.md"):
            return
    except OSError:
        pass

    flow_trace.record(
        inv.id, "runtime.finalizing", gave_up=gave_up, stop_reason=stop_reason,
        failure=flow_trace.safe_text(error) if error else None,
        budget_remaining=budget.remaining if budget else None,
        observation_count=obs_store.count(),
        graph_node_count=len(graph.all_nodes()),
        goals=flow_trace.goal_states(goals, obs_store.all()),
    )

    manager.update(inv.id, state=LifecycleState.reporting, last_event="generating report")
    # Persist state best-effort: a crash may have left a sub-store unhappy, but a
    # failure to persist one must not stop the report or the terminal transition.
    for persist in (graph.persist, kg.persist, goals.persist):
        try:
            persist()
        except Exception as exc:  # noqa: BLE001
            log.warning("investigation %s: %s failed during finalize: %s",
                        inv.id, getattr(persist, "__qualname__", persist), exc)

    report_path = None
    try:
        from wizard_kernel.control.report import generate
        report_md = generate(inv, graph, obs_store.all(), kg, goals, failure=error)
        report_path = fs_store.write_text(inv.id, "verification_report.md", report_md)
        bus.emit(event_bus.ReportGenerated, {"path": str(report_path)})
    except Exception as exc:  # noqa: BLE001 — a report failure must not erase the primary error
        log.warning("investigation %s: report generation failed during finalize: %s",
                    inv.id, exc)

    # ── Terminal state ────────────────────────────────────────────────────────
    if error is not None:
        # Wizard malfunctioned. Honest terminal state; the original error wins.
        manager.update(inv.id, state=LifecycleState.failed,
                       last_event=f"fatal: {error}", error=error,
                       active_goals=goals.to_api_list(obs_store.all()))
        flow_trace.record(inv.id, "runtime.terminal", state="failed",
                          reason=flow_trace.safe_text(error), report="verification_report.md")
        return

    if goals.all_satisfied():
        manager.update(inv.id, state=LifecycleState.completed, last_event="complete",
                       active_goals=goals.to_api_list(obs_store.all()))
        flow_trace.record(inv.id, "runtime.terminal", state="completed",
                          reason="all goal requirements satisfied",
                          report="verification_report.md")
        return

    # Did the *application* stop us, or did Wizard run out of ideas? If an open
    # goal needs runtime evidence and the observations hold a clear external
    # failure — a start/exec command that exited non-zero, or an endpoint that
    # never came up — the honest terminal state is `blocked`, naming the real
    # boundary, not a vague "incomplete" that buries it under a list of goals.
    blocker = _external_blocker(obs_store)
    open_goals = [g.name for g in goals.open_goals()]
    needs_runtime = any(getattr(g, "requires_execution_evidence", False)
                        for g in goals.open_goals())
    if blocker and (needs_runtime or not any(
            getattr(g, "requires_execution_evidence", False) for g in goals.all())):
        last_event = f"blocked: {blocker}"
        log.info("investigation %s blocked: %s", inv.id, blocker)
        bus.emit(event_bus.InvestigationIncomplete,
                 {"reason": blocker, "open_goals": open_goals, "classification": "blocked"})
        manager.update(inv.id, state=LifecycleState.blocked, last_event=last_event,
                       active_goals=goals.to_api_list(obs_store.all()))
        flow_trace.record(inv.id, "runtime.terminal", state="blocked",
                          reason=blocker, open_goals=open_goals,
                          report="verification_report.md")
        return

    if gave_up:
        reason = stop_reason or "the planner proposed no further steps"
    elif budget is not None and budget.is_exhausted():
        reason = "the budget ran out"
    else:
        reason = "the loop ended"
    last_event = (f"{reason}; still open: " + ", ".join(open_goals)
                  if open_goals else f"{reason}; the plan defined no goals")
    log.info("investigation %s ended incomplete: %s", inv.id, last_event)
    bus.emit(event_bus.InvestigationIncomplete,
             {"reason": reason, "open_goals": open_goals})
    manager.update(inv.id, state=LifecycleState.incomplete, last_event=last_event,
                   active_goals=goals.to_api_list(obs_store.all()))
    flow_trace.record(inv.id, "runtime.terminal", state="incomplete",
                      reason=reason, open_goals=open_goals,
                      report="verification_report.md")


def _external_blocker(obs_store: ObservationStore) -> str | None:
    """A one-line reason the *application*, not Wizard, prevented verification.

    Scans observations for the two unambiguous external-failure signatures and
    returns the most informative one, or None when there is no such evidence (in
    which case the run is genuinely `incomplete`, not `blocked`). Deliberately
    narrow: only the application's own process/port tools count, never an agent
    or seam failure — misclassifying a Wizard defect as an environmental blocker
    is the one thing this must not do.

    1. A start/exec command that exited non-zero — the app refused to boot. The
       command's stderr tail is the actionable part (e.g. a required env var).
    2. A readiness probe (`check_port`) that stayed inactive with no later probe
       of the same port ever going active — nothing ever listened.

    Gated on reachability: if the application became reachable by ANY means —
    an active port, a successful HTTP response from a loopback host, or a browser
    navigation that returned a status — then it is NOT externally blocked, and
    neither a stray failed command (a build, a one-off probe) nor an inactive
    probe of a *different* port that the agent happened to guess can say
    otherwise. Without this gate a run whose app answered on :5173 was reported
    `blocked: nothing listened on :80` because the agent probed :80 once — a
    false blocker that buried a working application and an unfinished agent
    decision underneath it.
    """
    observations = obs_store.all()

    def _reachable(obs) -> bool:
        payload = obs.payload or {}
        data = payload.get("data") or {}
        if obs.source_tool == "check_port" and data.get("active"):
            return True
        if obs.source_tool == "http_request" and payload.get("ok"):
            url = str(data.get("url") or payload.get("url") or "")
            return any(h in url for h in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"))
        if obs.source_tool == "browser_navigate" and payload.get("ok"):
            return data.get("status") is not None or bool(data.get("url"))
        return False

    if any(_reachable(o) for o in observations):
        # The application answered. Whatever else failed, the boundary that
        # stopped verification was not "the app never came up".
        return None

    # (1) a failed start/exec, OR a server that crashed after starting. A
    # background server started with start_process reports success and
    # `is_running` immediately — its crash only shows up in a later read_process
    # as a non-zero exit, which is exactly how `npm run dev` dying with
    # "Cannot find module …" was reported as a generic "a start command" failure:
    # the real command and error live on the read_process observation, so scan
    # those too and name the actual command and its output.
    for obs in reversed(observations):
        if obs.source_tool not in ("execute_command", "start_process", "read_process"):
            continue
        payload = obs.payload or {}
        data = payload.get("data") or {}
        exit_code = payload.get("exit_code", data.get("exit_code"))
        # A read_process for a still-running server is not a failure; only a
        # process that has EXITED non-zero is.
        if obs.source_tool == "read_process":
            running = data.get("is_running", payload.get("is_running"))
            if running or not (isinstance(exit_code, int) and exit_code != 0):
                continue
        if payload.get("ok") is False or (isinstance(exit_code, int) and exit_code != 0):
            stderr = (payload.get("stderr") or data.get("stderr")
                      or data.get("stderr_so_far") or data.get("stdout_so_far")
                      or payload.get("stdout") or "").strip()
            cmd = (data.get("command") or payload.get("command") or "a start command")
            tail = " ".join(stderr.split())[:200]
            if tail:
                return f"the application did not start: `{cmd}` exited {exit_code}: {tail}"
            if payload.get("ok") is False or (isinstance(exit_code, int) and exit_code != 0):
                return f"the application did not start: `{cmd}` exited {exit_code}"
    # (2) a port probed but never active.
    active_ports, inactive_ports = set(), {}
    for obs in observations:
        if obs.source_tool != "check_port":
            continue
        data = (obs.payload or {}).get("data") or {}
        port = data.get("port")
        if data.get("active"):
            active_ports.add(port)
        elif port is not None:
            inactive_ports[port] = True
    dead = [p for p in inactive_ports if p not in active_ports]
    if dead:
        return (f"no service ever listened on port {', '.join(map(str, dead))}; "
                f"the application never became reachable")
    return None



# ── Phase 6 helpers ───────────────────────────────────────────────────────────

def _resolve_tool_action(
    node: InvestigationNode,
    explorer: "ExplorerPort",
    context: dict,
    validator: ToolRequestValidator,
    budget: BudgetManager,
    bus: event_bus.EventBus,
    observations: list | None = None,
) -> tuple[dict | None, dict | None]:
    """Ask the Explorer Agent for a ToolRequest and validate it deterministically.

    Returns the sanitised action and no failure on success; otherwise a safe,
    structured failure that the loop persists with the current goal/node.
    A failed or invalid Explorer decision is not replaced with the Planner's action.

    Emits the B8 decision-narration events (agent.decided / tool.rejected) so every
    watch surface can see WHY the runtime chose an action — not browser-specific,
    this lights up the file-investigation flow too.
    """
    # Ask the Explorer Agent — it must return a ToolRequest
    inv_id = str(context.get("investigation_id", "unknown"))
    flow_trace.record(inv_id, "explorer.request", explorer=type(explorer).__name__,
                      node_id=node.id,
                      context=flow_trace.context_summary(context, observations))
    explorer_started = time.monotonic()
    try:
        response = explorer.request(context)
        agent_request = response.tool_request
    except Exception as exc:  # noqa: BLE001 — agent failure never crashes (invariant 4)
        http_response = getattr(exc, "response", None)
        status = getattr(exc, "status_code", None) or getattr(http_response, "status_code", None)
        detail = getattr(exc, "detail", None) or getattr(http_response, "text", None)
        if detail is None and callable(getattr(exc, "errors", None)):
            detail = "; ".join(
                f"{'.'.join(map(str, item.get('loc', ())))}: {item.get('msg', '')}"
                for item in exc.errors(include_input=False)
            ) or "Explorer response failed schema validation"
        if detail is None:
            detail = str(exc)
        request_id = getattr(exc, "request_id", None)
        if http_response is not None:
            headers = getattr(http_response, "headers", {})
            request_id = request_id or headers.get("x-request-id") or headers.get("request-id")
        import re
        detail = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", str(detail))
        detail = re.sub(
            r"(?i)\b(?:[A-Z0-9_]*API[_-]?KEY|[A-Z0-9_]*_KEY|TOKEN|SECRET|PASSWORD)\b\s*[:=]\s*\S+",
            "[REDACTED]",
            detail,
        )[:500]
        error_type = "EXPLORER_PROVIDER_ERROR"
        if detail.startswith("unusable kernel packet:"):
            error_type = "EXPLORER_CONTEXT_REJECTED"
        elif "output failed validation" in detail.lower():
            error_type = "EXPLORER_OUTPUT_INVALID"
        log.warning(
            "%s investigation=%s node=%s status=%s request_id=%s model=%s detail=%s",
            error_type, context.get("investigation_id", "unknown"), node.id,
            status if status is not None else "unknown", request_id or "unknown",
            context.get("model", "unknown"), detail,
        )
        flow_trace.record(inv_id, "explorer.failure", node_id=node.id,
                          elapsed_ms=int((time.monotonic() - explorer_started) * 1000),
                          failure_kind=error_type, http_status=status,
                          request_id=request_id, model=context.get("model"), detail=detail)
        return None, {
            "error_type": error_type,
            "status": status,
            "detail": detail,
            "provider_request_id": request_id,
            "model": context.get("model", "unknown"),
        }

    # If agent returned a request, validate it
    if agent_request is not None:
        tool_request_id = uuid.uuid4().hex
        flow_trace.record(inv_id, "explorer.tool_request", node_id=node.id,
                          tool_request_id=tool_request_id,
                          elapsed_ms=int((time.monotonic() - explorer_started) * 1000),
                          tool=agent_request.tool,
                          parameters=flow_trace.safe_parameters(agent_request.parameters),
                          reason_chars=len(agent_request.reason or ""))
        validation = validator.validate(agent_request, budget.remaining)
        if validation.valid:
            flow_trace.record(inv_id, "runtime.validation", node_id=node.id,
                              result="accepted", tool=agent_request.tool,
                              tool_request_id=tool_request_id,
                              parameters=flow_trace.safe_parameters(validation.sanitised_params))
            bus.emit(event_bus.AgentDecided, {
                "node_id": node.id, "source": "explorer",
                "tool": agent_request.tool, "reason": agent_request.reason,
                # The sanitised parameters, i.e. exactly what is about to be
                # executed. A decision line that names only the tool cannot tell
                # a reader which file was read or which command was run, so the
                # trace showed a run of anonymous "read_file"s and the work the
                # investigation actually did was invisible on it.
                "params": validation.sanitised_params,
            })
            # Use agent's suggested tool with sanitised parameters
            return ({"tool": agent_request.tool, "params": validation.sanitised_params,
                     "tool_request_id": tool_request_id}, None)
        else:
            request_id = tool_request_id
            flow_trace.record(inv_id, "runtime.validation", node_id=node.id,
                              result="rejected", tool=agent_request.tool,
                              parameters=flow_trace.safe_parameters(agent_request.parameters),
                              reason=validation.reason, tool_request_id=request_id)
            bus.emit(event_bus.ToolRejected, {
                "node_id": node.id, "tool": agent_request.tool, "reason": validation.reason,
                "tool_request_id": request_id,
                # Same reason the accepted path carries them: a refusal that names
                # only the tool forces the reader to guess which file or command
                # was refused, and on a duplicate it hides the very path that
                # explains the refusal.
                "params": {key: type(value).__name__
                           for key, value in agent_request.parameters.items()},
            })
            log.warning(
                "Explorer agent ToolRequest rejected for node %s: %s",
                node.id, validation.reason,
            )
            return None, {
                "error_type": "TOOL_REQUEST_REJECTED",
                "tool": agent_request.tool,
                "detail": validation.reason[:500],
                "tool_request_id": request_id,
                "parameters": {key: type(value).__name__
                               for key, value in agent_request.parameters.items()},
            }

    flow_trace.record(inv_id, "explorer.failure", node_id=node.id,
                      elapsed_ms=int((time.monotonic() - explorer_started) * 1000),
                      failure_kind="EXPLORER_DECISION_FAILED",
                      detail="Explorer returned no ToolRequest")
    return None, {"error_type": "EXPLORER_DECISION_FAILED",
                  "detail": "Explorer returned no ToolRequest"}


def _consult_verifier(
    inv: Investigation,
    verifier: "VerifierPort",
    kg: KnowledgeGraph,
    goals: GoalEngine,
    graph: InvestigationGraph,
    planner: "PlannerPort",
    plan: TechnologyPlan,
    budget: BudgetManager,
    obs_store: ObservationStore,
    bus: event_bus.EventBus,
    completed_ids: set[str] | None = None,
    escalate: bool = True,
) -> None:
    """Ask the Verifier Agent to review current claims.

    The Runtime reads the Verifier's assessment and independently decides
    whether to act. The Verifier CANNOT set trust, mark goals, or modify graphs.

    `escalate=False` records the assessment without asking the Planner for more
    work — used for the final review, where the Runtime has already decided the
    investigation is over.
    """
    claims_payload = [
        {
            "claim_id": c.id,
            "type": c.claim_type,
            "key": c.key,
            "value": str(c.value),
            # Provenance, not trust (invariant 3). The Verifier's job is to judge
            # whether evidence is good enough, which it cannot do if it is told
            # nothing about where the claim came from — an earlier revision sent
            # claim text alone, so every claim looked equally unsupported and the
            # agent answered "needs_more_work" every single time. Tiers and
            # support/contradict are facts about the evidence; the numeric trust
            # score, the disbelief value, and the raw graph stay kernel-side.
            "evidence": [
                {
                    "evidence_id": ev.id,
                    "source_tier": ev.source_tier,
                    "support_type": ev.support_type,
                    "node_id": ev.node_id if hasattr(ev, "node_id") else None,
                }
                for ev in kg.evidence_for(c.id)
            ],
        }
        for c in kg.all_claims()
    ]

    if not claims_payload:
        return  # Nothing to review yet

    bus.emit(event_bus.AgentConsulted,
             {"agent_type": "verifier", "claims_reviewed": len(claims_payload)})
    flow_trace.record(inv.id, "verifier.request",
                      verifier=type(verifier).__name__, claims_reviewed=len(claims_payload),
                      claim_types=sorted({c.get("type", "") for c in claims_payload}),
                      evidence_observations=[o.id for o in obs_store.all()
                                             if o.evidence_categories][-20:])
    try:
        assessment = verifier.assess(claims_payload, inv.id)
    except Exception as exc:  # noqa: BLE001 — verifier failure is non-fatal (invariant 4)
        response = getattr(exc, "response", None)
        obs_store.append(
            node_id="verifier",
            source_tool="verifier",
            obs_type="agent_failure",
            payload={"ok": False, "error": "Verifier request failed",
                     "status_code": getattr(response, "status_code", None)},
        )
        log.warning("Verifier agent failed (HTTP %s): %s — continuing without assessment",
                    getattr(response, "status_code", "unknown"), exc)
        flow_trace.record(inv.id, "verifier.failure",
                          http_status=getattr(response, "status_code", None),
                          error=flow_trace.safe_text(exc))
        return

    flow_trace.record(inv.id, "verifier.response",
                      assessment=assessment.assessment,
                      weak_claims=assessment.weak_claims,
                      recommendations=assessment.recommended_additional_investigations,
                      runtime_authority="goal engine remains authoritative")

    log.info("Verifier assessment for %s: %s, weak_claims=%s",
             inv.id, assessment.assessment, assessment.weak_claims)

    # Record the verdict on the trace. Without this the Verifier's opinion only
    # ever appeared as a log line, so from the event stream alone it was
    # impossible to tell whether it had run, or what it thought.
    bus.emit(event_bus.AgentAssessed, {
        "agent_type": "verifier",
        "assessment": assessment.assessment,
        "claims_reviewed": len(claims_payload),
        "weak_claims": assessment.weak_claims,
        "recommended_additional_investigations":
            assessment.recommended_additional_investigations,
        "escalated": escalate,
    })

    # Runtime-only decision: if the Verifier thinks we need more work AND
    # there are weak claims, ask the Planner to generate additional investigation nodes.
    # The Verifier's opinion is advisory. The Runtime independently judges the situation.
    if (escalate
            and assessment.assessment == "needs_more_work"
            and assessment.recommended_additional_investigations):
        context = _planner_next_context(
            inv, goals, kg, plan, budget, obs_store, "verifier_identified_gaps",
            # The Verifier's own reading of the gaps is the reason we are calling at
            # all, so it replaces the goal-derived prose list. The structured
            # requirements still come from the goals — the Verifier does not get to
            # define what counts as evidence (invariant 2).
            missing_evidence=assessment.recommended_additional_investigations,
            weak_claims=assessment.weak_claims,
            graph=graph,
            completed_ids=completed_ids if completed_ids is not None else set(),
        )
        try:
            flow_trace.record(inv.id, "planner.next.request",
                              trigger="verifier_recommendation",
                              context=flow_trace.planner_context_summary(context))
            new_nodes = planner.next_nodes(context)
            flow_trace.record(inv.id, "planner.next.response",
                              trigger="verifier_recommendation",
                              proposed_nodes=[flow_trace.node_summary(n) for n in new_nodes])
            added = 0
            for n in new_nodes:
                if _already_scheduled(graph, completed_ids or set(), n):
                    flow_trace.record(inv.id, "planner.node.deduplicated",
                                      trigger="verifier_recommendation",
                                      proposed=flow_trace.node_summary(n),
                                      existing_node_count=len(graph.all_nodes()))
                    bus.emit(event_bus.PlannerNodeSkipped, {
                        "node_id": n.id, "type": n.type,
                        "reason": "a node for the same action is already queued",
                    })
                    continue
                graph.add(n)
                added += 1
            if added:
                log.info("Planner added %d nodes based on Verifier assessment for %s",
                         added, inv.id)
        except Exception as exc:  # noqa: BLE001
            log.warning("Planner failed to generate nodes from Verifier assessment: %s", exc)


def _missing_requirements(goals: GoalEngine, kg: KnowledgeGraph) -> list[dict]:
    """What evidence each open goal still needs, in structured form.

    Two consumers read this: the planner's validator and heuristic provider, which
    need `claim_type` as a field, and `_missing_evidence_list`, which renders the
    same gaps as prose. Emitting the structure once and deriving the prose from it
    keeps them from drifting — a prose-only packet made the planner recover the
    claim type by re-parsing a description string it had produced itself.
    """
    missing: list[dict] = []
    for g in goals.open_goals():
        for claim_type in g.required_claim_types:
            claims = kg.find(claim_type, None)
            if not claims:
                missing.append({
                    "claim_type": claim_type,
                    "goal_id": g.id,
                    "goal_name": g.name,
                    "expected_value": None,
                    "description": f"No claims of type {claim_type!r} for goal {g.name!r}",
                })
            elif g.requires_execution_evidence:
                # Check if any claim has execution-tier evidence
                has_exec = any(
                    any(ev.source_tier == "execution" for ev in kg.evidence_for(c.id))
                    for c in claims
                )
                if not has_exec:
                    missing.append({
                        "claim_type": claim_type,
                        "goal_id": g.id,
                        "goal_name": g.name,
                        "expected_value": None,
                        "description": (
                            f"Goal {g.name!r}: {claim_type!r} exists but lacks execution evidence"
                        ),
                    })
    return missing


def _missing_evidence_list(goals: GoalEngine, kg: KnowledgeGraph) -> list[str]:
    """The prose view of `_missing_requirements` — same gaps, same order."""
    return [r["description"] for r in _missing_requirements(goals, kg)]


def _active_technology(plan: TechnologyPlan, goals: GoalEngine) -> str:
    """The technology whose goals the investigation is actually working on.

    The planner's heuristic provider plans actions for one technology at a time.
    A plan usually lists several, so taking technologies[0] would target a
    technology that may already be satisfied; match on the open goals instead.
    """
    open_names = {g.name for g in goals.open_goals()}
    for tech in plan.technologies:
        if any(g.name in open_names for g in tech.initial_goals):
            return tech.name
    return plan.technologies[0].name if plan.technologies else "unknown"


def _priority_files(plan: TechnologyPlan, limit: int = 20) -> list[str]:
    """Files the plan flagged, de-duplicated in plan order."""
    ordered: dict[str, None] = {}
    for tech in plan.technologies:
        for path in tech.priority_files:
            ordered.setdefault(path, None)
    return list(ordered)[:limit]


def canonical_rel_path(path: str) -> str:
    """The one spelling this packet uses for a repository-relative path.

    A path reaches the planner from two directions that do not agree on the
    separator: the manifest's file list carries the platform's native form
    (``client\\src\\app.js`` on Windows), while this index is built from what the
    tool reported after ToolRequestValidator resolved it. Comparing the two
    literally makes every Windows file look unread, so the planner re-proposes a
    read of a file the Runtime has already read — and since the *validator*
    canonicalises before fingerprinting, that repeat is caught as a duplicate and
    the node is failed. The two sides disagree only about the separator, and only
    for display purposes, so both now use this form and neither can drift.

    It is a comparison key, not a path to hand to a tool: the Runtime resolves
    whatever spelling a tool request carries.
    """
    return path.replace("\\", "/")


def _observation_index(obs_store: ObservationStore) -> tuple[dict[str, str], dict[str, str]]:
    """(path -> obs id) for files already read, and for those already parsed.

    The planner's heuristic provider proposes a READ for any priority file absent
    from the first map, and a PARSE for any read file absent from the second
    (HeuristicLLMProvider::buildOngoingPlan steps 1-2). Omitting them made the
    planner re-propose files the Runtime had just read, and the duplicate-request
    validator then rejected the node — one wasted budget slot and one failed node
    per repeat.

    Keys are `canonical_rel_path`-normalised so a planner matches them whichever
    separator convention it holds; see that function for why that matters.

    "Parsed" is truthful, not aspirational: read_file already runs a JSON parse and
    records the result in data.parsed. The kernel has no standalone parse tool, so
    a file counts as parsed exactly when that field is populated.
    """
    read: dict[str, str] = {}
    parsed: dict[str, str] = {}
    for obs in obs_store.all():
        if obs.source_tool != "read_file" or not obs.payload.get("ok"):
            continue
        data = obs.payload.get("data") or {}
        meta = obs.payload.get("meta") or {}
        path = meta.get("path") or data.get("path")
        if not path:
            continue
        key = canonical_rel_path(path)
        read.setdefault(key, obs.id)
        if data.get("parsed") is not None:
            parsed.setdefault(key, obs.id)
    return read, parsed


def _node_action_fingerprint(action: dict) -> str:
    """A stable identity for "the same thing done to the same thing".

    The same shape the ToolRequestValidator fingerprints: tool plus sorted
    parameters. Two nodes that share one are two nodes that will issue the same
    tool request, which is what the validator refuses at execution time — after
    the node has already been created and will burn a budget slot to fail.
    """
    params = action.get("params") or {}
    return json.dumps([action.get("tool", ""), params], sort_keys=True, default=str)


def _already_scheduled(
    graph: "InvestigationGraph", completed_ids: set[str], node: InvestigationNode
) -> bool:
    """Is this planner node a repeat of one the graph already holds?

    The kernel owns the graph, so deciding what enters it is the kernel's call,
    not the planner's (invariant 3) — and adding a node the validator is going to
    refuse is a decision to waste a budget slot on a rejection. Skipped rather
    than quietly dropped: the skip is emitted so a planner that keeps proposing
    duplicates is visible instead of merely ineffective.

    Every state counts, including `failed`. The validator dedupes on
    (tool, params) for the whole investigation, so once an action has been
    *validated* it can never run again — and a node reaches `failed` either by
    running (fingerprint registered) or by being refused as a duplicate
    (fingerprint already registered). Either way a new node for the same action
    is guaranteed to be refused. Exempting failed nodes let a single failing
    command be re-proposed every round: nine copies, nine rejections, nine
    budget slots, and the run ended `incomplete` having learned nothing after
    the first attempt.

    Browser tools are the one exception, and for the same reason the validator
    makes it: identical parameters address a changed live page, so a repeat is
    a legitimate re-observation rather than a cycle.
    """
    action = node.action or {}
    if action.get("tool") in BROWSER_TOOLS:
        return False
    fp = _node_action_fingerprint(action)
    return any(
        _node_action_fingerprint(existing.action or {}) == fp
        for existing in graph.all_nodes()
    )


def _queued_read_paths(graph: "InvestigationGraph", completed_ids: set[str]) -> list[str]:
    """Files a node already in the graph is going to read, but has not read yet.

    `_observation_index` answers "what has been read". That is not the same as
    "what is already being taken care of", and the planner was only told the
    first. A batch of read nodes proposed by one /plan/next can sit queued behind
    goal-priority scoring while a second call — the main loop's, then the
    Verifier escalation's — is made against the same observation state and
    proposes the identical reads again. Both batches go into the graph, the first
    one reads the file, and the second one's requests are then rejected as
    duplicates: a failed node and a spent budget slot per file, for work that was
    already scheduled.

    Telling the planner what is queued is what lets it stop proposing it. Only
    pending nodes count — a completed node's file is in the observation index by
    definition, and a failed one's file still needs reading.
    """
    queued: dict[str, None] = {}
    for n in graph.all_nodes():
        if n.id in completed_ids or n.state == "running":
            continue
        action = n.action or {}
        if action.get("tool") != "read_file":
            continue
        path = (action.get("params") or {}).get("path")
        if path:
            queued.setdefault(canonical_rel_path(str(path)), None)
    return list(queued)


def _visited_urls(obs_store: ObservationStore) -> list[str]:
    """URLs this investigation has already navigated to, in first-seen order.

    The browser analog of `_observation_index`: without it the planner re-proposes
    a navigate to a page the Runtime has already observed, and since browser tools
    are exempt from duplicate-request dedup that repeat costs a budget slot rather
    than being rejected.
    """
    seen: dict[str, None] = {}
    for obs in obs_store.all():
        if obs.obs_type not in ("browser_action", "page_content"):
            continue
        url = (obs.payload.get("data") or {}).get("url")
        if url:
            seen.setdefault(url, None)
    return list(seen)


def _page_state(obs_store: ObservationStore) -> dict:
    """What the most recently observed page looked like.

    `_visited_urls` answers "which pages have been seen". That is not enough to
    write an interaction script: a step names a *control*, and the only place a
    control's role and accessible name exist is the observation of the page that
    offered it. Sending URLs alone meant the planner could see that a page had
    been visited and never what was on it, so it could propose a navigate and
    nothing else — which is exactly the read-only walk this replaces.

    The LAST page-shaped observation wins, not the first: the script continues
    from where the run currently is, and after a click the current page is the
    one the click produced. `controls` is only ever present on a snapshot or an
    extract, so a navigate (which carries the url but no controls) updates the
    url without blanking the control list the run is still working from.

    `interacted_selectors` rides along for the reason `visited_urls` does, one
    level down: browser tools are exempt from duplicate-request dedup (identical
    params address a changed page), so a planner that cannot see which controls
    have already been pressed proposes the same fill again on every call, and
    each repeat costs a budget slot and re-types over whatever the first one set.
    """
    url, controls, fingerprint = "", [], ""
    acted: dict[str, None] = {}
    for obs in obs_store.all():
        if obs.obs_type not in ("browser_action", "page_content"):
            continue
        payload_data = obs.payload.get("data") or {}
        # A page-changing click/type/fill stores the resulting page under
        # `page_observation` (the pre-action top level has only the action
        # result). Prefer it so the planner plans against the page the run is
        # NOW on — without this, after clicking "Create one" the planner kept
        # seeing the login page's controls, proposed actions that no longer
        # matched, and the run oscillated between links instead of filling the
        # form it had just reached. Matches what the Explorer packager already does.
        page = payload_data.get("page_observation") or payload_data
        if page.get("url"):
            url = page["url"]
        if page.get("controls"):
            controls = page["controls"]
        if page.get("page_fingerprint"):
            fingerprint = page["page_fingerprint"]
        # The action itself (what was pressed/typed) is on the top-level data,
        # not inside the nested page snapshot.
        selector = payload_data.get("selector")
        if selector and (payload_data.get("clicked") or payload_data.get("typed")):
            acted.setdefault(selector, None)
        # A batched form fill records each field it typed under `fields`.
        for field in (payload_data.get("fields") or []):
            if isinstance(field, dict) and field.get("typed") and field.get("selector"):
                acted.setdefault(field["selector"], None)
    return {
        "page_url": url,
        "page_controls": controls,
        "page_fingerprint": fingerprint,
        "interacted_selectors": list(acted),
    }


def _planned_action_matches(planned: dict | None, actual_tool: str, actual_params: dict) -> bool:
    """Whether this observation can support the Planner's action-specific claim."""
    if not isinstance(planned, dict) or planned.get("tool") != actual_tool:
        return False
    expected = planned.get("params") or planned.get("parameters") or {}
    return isinstance(expected, dict) and all(actual_params.get(key) == value
                                               for key, value in expected.items())


def _planner_next_context(
    inv: Investigation,
    goals: GoalEngine,
    kg: KnowledgeGraph,
    plan: TechnologyPlan,
    budget: BudgetManager,
    obs_store: ObservationStore,
    reason: str,
    graph: "InvestigationGraph | None" = None,
    completed_ids: set[str] | None = None,
    **extra: object,
) -> dict:
    """The /plan/next packet.

    The planner's HTTP adapter reads a flat packet and pulls named keys out of it
    (http/server.ts::heuristicFrom). The keys that actually drive its heuristic
    provider are the structured ones: missing_requirements, goal_technology,
    priority_files, allow_execution, file_observation_ids. Sending only kg_summary
    and prose missing_evidence left all of them absent, so the provider planned for
    "unknown" technology against no requirements and could only ever answer with an
    empty batch — the loop then broke out with goals still open.

    allow_execution is stated here because the Runtime owns the sandbox decision
    (invariant 2): the planner may *propose* a command, but the kernel's
    ToolRequestValidator is what admits it. Telling the planner the truth up front
    is what lets it propose execution nodes the kernel then accepts or rejects on
    its own terms.
    """
    file_obs, parsed_obs = _observation_index(obs_store)
    context: dict = {
        "investigation_id": inv.id,
        "reason": reason,
        "kg_summary": kg.summary(),
        "missing_evidence": _missing_evidence_list(goals, kg),
        "missing_requirements": _missing_requirements(goals, kg),
        "goal_technology": _active_technology(plan, goals),
        "priority_files": _priority_files(plan),
        "allow_execution": True,
        "budget_remaining": budget.remaining,
        "repo_root": inv.repository_path,
        "file_observation_ids": file_obs,
        "parsed_observation_ids": parsed_obs,
        # What is already scheduled, as opposed to what has already run. The two
        # answer different questions and the planner needs both: the indexes
        # above stop it re-reading a file, this stops it re-proposing a read that
        # is sitting in the graph waiting its turn. Without it, a second
        # /plan/next call sees the same observation state as the first and
        # returns the same batch, and the copies are rejected as duplicates when
        # their turn comes.
        "queued_read_paths": (
            _queued_read_paths(graph, completed_ids)
            if graph is not None and completed_ids is not None else []
        ),
        # Browser facts, for the same reason allow_execution is here: the planner
        # may propose a browser action, but it can only do so if it knows the plane
        # exists, which hosts the egress allowlist admits, and which URLs the user
        # actually named. The kernel still validates every URL at execution time —
        # this tells the planner the truth, it does not grant it permission.
        "browser_enabled": bool(inv.options.get("browser_enabled")),
        "allowed_domains": list(inv.options.get("allowed_domains") or []),
        "browser_targets": [t for t in inv.targets if str(t).startswith(("http://", "https://"))],
        "visited_urls": _visited_urls(obs_store),
        # And what the page SHOWED, not just that it was visited. A control's role
        # and accessible name exist in exactly one place — the observation of the
        # page that offered it — so without this the planner can name a URL and
        # cannot name a single thing on it. That is the whole difference between
        # proposing a navigate and proposing an interaction.
        **_page_state(obs_store),
        # The user's own words, for the same reason again. The initial plan is
        # built from these, and this packet is what a planner reads when that
        # plan runs out of steps. Sending neither meant the ongoing phase could
        # only ever work on goals the initial phase had already thought of, so a
        # question the initial plan missed stayed missed for the whole run.
        "intent": inv.intent,
        "targets": list(inv.targets),
        # And what the user actually typed, which `intent` above is not. That key
        # is the command FAMILY — one of four verbs — and the initial call already
        # learned that reading a family as the user's words turns `explain` into a
        # subject to go and read. The ongoing phase needs the difference for the
        # same reason and one more: whether a run may press a page's controls is
        # decided by what was asked, and only this key holds what was asked.
        "question": inv.question,
    }
    context.update(extra)
    return context


# ── Helpers ───────────────────────────────────────────────────────────────────

def _current_page(tools: ToolExecutor) -> dict | None:
    """The page as it stands after a browser action, for the event to carry.

    Read fresh rather than lifted out of the action's own result, because most
    actions do not return one. `browser_navigate` returns a url and a title and
    knows nothing about controls; `browser_click` returns the fingerprint it
    compared before and after and, for the same reason, no controls. Only
    `browser_snapshot` and `browser_extract` read the page's controls at all — so
    a pane fed from the action results would go blank on every navigate and show
    the page as it was before a click that had already changed it.

    Reading it here costs one round trip to the page on an action that just spent
    several hundred milliseconds driving a real browser, and it buys the one thing
    a viewer wants: the page as it is now, not as the run last happened to look.

    Nothing about a viewer's read may end a run, so this cannot raise. A browser
    that is gone, a page that closed under us, or a runtime that does not offer
    the read at all all mean the same thing here — no page to show this time —
    and the pane keeps the last one it had.
    """
    browser = getattr(tools, "browser", None)
    if browser is None:
        return None
    try:
        return browser.page_view()
    except Exception:  # noqa: BLE001 — narration never fails a run (invariant 4's spirit)
        log.debug("page view unavailable for narration", exc_info=True)
        return None


def _emit_browser_narration(bus: event_bus.EventBus, tool_name: str, data: dict,
                            page: dict | None = None) -> None:
    """Emit the discrete browser.* narration event for a successful browser action.

    Narration only: the live picture streams over the screencast WebSocket and
    never enters EventBus history (two-plane model — see architecture §1).

    Every one of these events carries `page` — the whole page as text: where it
    is, and every control on it. It is the same reading for all three because a
    viewer's question is the same after all three ("what am I looking at now?"),
    and because the alternative — each event carrying its own slice — leaves the
    pane reconstructing a page out of three partial ones and showing a state the
    browser was never in.
    """
    common = {"page": page} if page is not None else {}
    if tool_name in ("browser_navigate", "browser_back"):
        bus.emit(event_bus.BrowserNavigated, {
            "url": data.get("url"), "status": data.get("status"), "title": data.get("title"),
            **common,
        })
    elif tool_name in ("browser_click", "browser_type"):
        # What was done to the control, and — for an interaction — what it did
        # back. `effect` and `value` are the two answers the run exists to get,
        # and a narration that showed only the selector would leave the trace
        # reporting that a button was pressed without ever saying whether
        # anything happened.
        bus.emit(event_bus.BrowserActed, {
            "tool": tool_name, "url": data.get("url"), "selector": data.get("selector"),
            # What the control is called, captured by the runtime while it still
            # existed. A viewer reads this instead of the selector, and needs it
            # most in the case where the control is now gone — a click that
            # navigated took its own button with it.
            "selector_name": data.get("selector_name"),
            "effect": data.get("effect"), "value": data.get("value"),
            **common,
        })
    elif tool_name in ("browser_snapshot", "browser_extract"):
        bus.emit(event_bus.BrowserExtracted, {
            "url": data.get("url"), "title": data.get("title"),
            "node_count": data.get("node_count"),
            "link_count": len(data.get("links", []) or []),
            **common,
        })


def _safe_execute(tools: ToolExecutor, action: dict) -> dict:
    """Invariant 4: any exception becomes an error payload, never a crash."""
    try:
        return tools.execute(action)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "exit_code": -1, "error": str(exc)}
