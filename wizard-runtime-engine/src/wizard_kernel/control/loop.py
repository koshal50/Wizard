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
import uuid
from typing import TYPE_CHECKING

from wizard_kernel.belief import extractors
from wizard_kernel.belief.evidence import EvidenceEngine
from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.belief.trust import source_tier_for_tool
from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.node import InvestigationNode
from wizard_kernel.contracts.plan import TechnologyPlan
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.context.engine import ContextEngine
from wizard_kernel.control import hypothesis as hyp_eval
from wizard_kernel.control.goals import Goal, GoalEngine
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
    "browser_back":     "browser_action",
    "browser_snapshot": "page_content",
    "browser_extract":  "page_content",
}

# How many nodes complete before the Verifier Agent is consulted
_VERIFIER_INTERVAL = 5


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

    try:
        sandbox.start(inv.repository_path)
        if browser is not None:
            browser.start()
            browser_mod.register_runtime(inv.id, browser)
        tools = ToolExecutor(sandbox, inv.repository_path, browser=browser)
        _run_loop(inv, manager, planner, explorer, verifier, kg, ev_engine, graph, goals,
                  obs_store, tools, budget, bus, validator, completed_ids, context_engine)
    except Exception as exc:  # noqa: BLE001
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
    manifest = scanner.scan(inv.repository_path, inv.id)
    fs_store.write(inv.id, "manifest.json", manifest.model_dump())

    # ── Planning ──────────────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.planning, last_event="initial planner call")
    # inv.options is passed through because the planner is what decides whether to
    # plan a browser phase, and it can only do that if it is told a browser plane
    # exists (browser_enabled) and which hosts are reachable (allowed_domains).
    # inv.question rides along for the same reason: the planner plans what the
    # user asked, and `intent` — the command family — is not what they asked.
    # Passed by keyword, unlike the four before it, so an implementation still on
    # the old four-parameter signature fails with "got an unexpected keyword
    # argument 'question'" instead of a bare arity error that reads as a mystery.
    plan = planner.initial(
        manifest, inv.intent, inv.targets, inv.options, question=inv.question
    )
    fs_store.write(inv.id, "plan.json", plan.model_dump())

    # Goal requirements come ENTIRELY from GoalDefinition — invariant 5
    for tech in plan.technologies:
        for goal_def in tech.initial_goals:
            goals.add(Goal(
                id=f"goal_{uuid.uuid4().hex[:6]}",
                name=goal_def.name,
                required_claim_types=goal_def.required_claim_types,
                belief_threshold=goal_def.belief_threshold,
                requires_execution_evidence=goal_def.requires_execution_evidence,
            ))

    for node in plan.seed_nodes:
        graph.add(node)

    manager.update(inv.id, state=LifecycleState.investigation_loop,
                   last_event="loop started", active_goals=goals.to_api_list())
    bus.emit(event_bus.InvestigationStarted, {"repository_path": inv.repository_path})

    nodes_since_last_verify = 0
    final_review_done = False
    # Why the loop stopped. Set only on the give-up path; the other two exits
    # are read off the budget and the goals when the loop is over.
    gave_up = False

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
            new_nodes = planner.next_nodes(
                _planner_next_context(inv, goals, kg, plan, budget, obs_store, "need_more_work",
                                      graph=graph, completed_ids=completed_ids)
            )
            if not new_nodes:
                # The Planner has no further steps to propose. That is the run
                # running out of ideas, not the run finishing — recorded so the
                # report can say which of the two happened.
                gave_up = True
                break
            for n in new_nodes:
                if _already_scheduled(graph, completed_ids, n):
                    bus.emit(event_bus.PlannerNodeSkipped, {
                        "node_id": n.id, "type": n.type,
                        "reason": "a node for the same action is already queued",
                    })
                    continue
                graph.add(n)
            continue

        graph.set_state(node.id, "running")
        manager.update(inv.id, last_event=f"executing {node.id} ({node.type})")

        # ── Phase 6: Explorer Agent determines HOW to execute this node ───────
        # Context Engine builds the trust-stripped packet (agent contract) plus the
        # modular section view that drives KV-cache ordering + audit (invariant 3).
        ctx = context_engine.build_context("explorer", inv, node, goals, kg, budget, obs_store)
        tool_action = _resolve_tool_action(node, explorer, ctx.packet, validator, budget, bus)

        if tool_action is None:
            # Validation failed — mark node failed, record the rejection as an observation
            obs = obs_store.append(
                node_id=node.id,
                source_tool=node.action.get("tool", "unknown"),
                obs_type="command_result",
                payload={"ok": False, "exit_code": -1,
                         "error": "Tool request rejected by validator"},
            )
            graph.mark_failed(node.id, obs_ids=[obs.id])
            completed_ids.add(node.id)
            budget.consume()
            manager.update(inv.id, budget_remaining=budget.remaining,
                           nodes_completed=inv.nodes_completed + 1)
            bus.emit(event_bus.NodeFailed, {"node_id": node.id, "type": node.type,
                                            "reason": "validation_rejected"})
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
        # This is what lets the trace narrate an executing step with no LLM in the
        # picture at all: the tool and its params come from the plan's own
        # decision, so an offline run narrates itself as fully as a wired one.
        bus.emit(event_bus.NodeStarted, {
            "node_id": node.id,
            "type": node.type,
            "tool": tool_action.get("tool", "unknown"),
            "params": tool_action.get("params", {}) or {},
            "goal_id": node.goal_id,
        })

        # Execute — failures become observations, never crashes (invariant 4)
        payload = _safe_execute(tools, tool_action)

        # Immutable observation (invariant 1)
        tool_name = tool_action.get("tool", "unknown")
        obs = obs_store.append(
            node_id=node.id,
            source_tool=tool_name,
            obs_type=_TOOL_TO_OBS_TYPE.get(tool_name, "command_result"),
            payload=payload,
        )

        # Narration plane: discrete browser.* events on the EventBus. Pixels stream
        # separately over the screencast WebSocket and never enter event history.
        if tool_name.startswith("browser_") and payload.get("ok"):
            _emit_browser_narration(bus, tool_name, payload.get("data", {}) or {},
                                    page=_current_page(tools))

        # ── Deterministic hypothesis evaluation (invariant 3 — no LLM needed) ─
        source_tier = source_tier_for_tool(tool_name)
        node_outcome = hyp_eval.evaluate(node, obs)
        new_claims_this_node = 0

        match node_outcome:
            case "expected_success" if node.on_success:
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
            case "expected_failure" if node.on_failure:
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
            case _:
                # Unexpected — escalate to Planner (invariant 3: Planner never writes KG)
                for n in planner.interpret(node, obs):
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
        goals.evaluate_all(kg)
        for g in goals.all():
            if g.state == "satisfied" and g.id not in satisfied_before:
                bus.emit(event_bus.GoalSatisfied, {"goal_id": g.id, "goal_name": g.name})

        # ── Complete or fail the node in the graph ────────────────────────────
        if node_outcome in ("expected_success", "expected_failure"):
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
            bus.emit(event_bus.NodeFailed, {"node_id": node.id, "type": node.type})

        completed_ids.add(node.id)
        budget.consume()
        nodes_since_last_verify += 1

        manager.update(
            inv.id,
            budget_remaining=budget.remaining,
            nodes_completed=inv.nodes_completed + 1,
            claims_count=inv.claims_count + new_claims_this_node,
            active_goals=goals.to_api_list(),
        )

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
                    goals.mark_satisfied(ckpt.goal_id)

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

    # ── Report ────────────────────────────────────────────────────────────────
    # The cancel check at the top of the loop only fires between nodes, so a
    # cancel that lands after the last node — while the goals are being closed
    # out — arrives here instead. Generating a report for a run the user stopped
    # is work nobody asked for, and the manager will refuse the state change
    # anyway, so stop before writing anything.
    if inv.state == LifecycleState.cancelled:
        log.info("investigation %s was cancelled before reporting; not completing it.", inv.id)
        return

    manager.update(inv.id, state=LifecycleState.reporting, last_event="generating report")
    graph.persist()
    kg.persist()
    goals.persist()

    from wizard_kernel.control.report import generate
    report_md = generate(inv, graph, obs_store.all(), kg, goals)
    report_path = fs_store.write_text(inv.id, "verification_report.md", report_md)
    # Absolute, not the ".wizard/investigations/<id>/..." shape it used to emit.
    # That path is relative to *this process's* working directory, which is not
    # the directory of anyone reading the event — the Engine runs as its own
    # process, and a watcher, a CLI and a browser all sit elsewhere. Printed as
    # written it named a file that could not be opened from where it was read,
    # which is the whole of "the report is missing".
    bus.emit(event_bus.ReportGenerated, {"path": str(report_path)})

    # ── Terminal state ────────────────────────────────────────────────────────
    # What the run actually achieved, not what a report was written for. The
    # loop can end three ways, and they used to be indistinguishable: every one
    # of them reported `completed`. A run that satisfied its goals and a run
    # that ran out of steps both said "complete", which is how a partial
    # investigation came to read as a verified one.
    satisfied = goals.all_satisfied()
    if satisfied:
        state, last_event = LifecycleState.completed, "complete"
    else:
        state = LifecycleState.incomplete
        if gave_up:
            reason = "the planner proposed no further steps"
        elif budget.is_exhausted():
            reason = "the budget ran out"
        else:
            reason = "the loop ended"
        open_goals = [g.name for g in goals.open_goals()]
        last_event = (f"{reason}; still open: " + ", ".join(open_goals)
                      if open_goals else f"{reason}; the plan defined no goals")
        log.info("investigation %s ended %s: %s", inv.id, state.value, last_event)
        bus.emit(event_bus.InvestigationIncomplete,
                 {"reason": reason, "open_goals": open_goals})

    manager.update(inv.id, state=state, last_event=last_event,
                   active_goals=goals.to_api_list())


# ── Phase 6 helpers ───────────────────────────────────────────────────────────

def _resolve_tool_action(
    node: InvestigationNode,
    explorer: "ExplorerPort",
    context: dict,
    validator: ToolRequestValidator,
    budget: BudgetManager,
    bus: event_bus.EventBus,
) -> dict | None:
    """Ask the Explorer Agent for a ToolRequest and validate it deterministically.

    Returns the sanitised action dict on success, None on validation failure.
    Falls back to the node's own action if the agent fails or returns an invalid request.

    Emits the B8 decision-narration events (agent.decided / tool.rejected) so every
    watch surface can see WHY the runtime chose an action — not browser-specific,
    this lights up the file-investigation flow too.
    """
    # Ask the Explorer Agent — it must return a ToolRequest
    try:
        response = explorer.request(context)
        agent_request = response.tool_request
    except Exception as exc:  # noqa: BLE001 — agent failure never crashes (invariant 4)
        log.warning("Explorer agent failed for node %s: %s — falling back to node action",
                    node.id, exc)
        agent_request = None

    # If agent returned a request, validate it
    if agent_request is not None:
        validation = validator.validate(agent_request, budget.remaining)
        if validation.valid:
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
            return {"tool": agent_request.tool, "params": validation.sanitised_params}
        else:
            bus.emit(event_bus.ToolRejected, {
                "node_id": node.id, "tool": agent_request.tool, "reason": validation.reason,
                # Same reason the accepted path carries them: a refusal that names
                # only the tool forces the reader to guess which file or command
                # was refused, and on a duplicate it hides the very path that
                # explains the refusal.
                "params": agent_request.parameters,
            })
            log.warning(
                "Explorer agent ToolRequest rejected for node %s: %s — falling back to node action",
                node.id, validation.reason,
            )

    # Fallback: use the node's own pre-planned action (from Planner)
    # The node action was already generated by the Planner — it's trusted but still validated
    fallback_request = ToolRequest(
        tool=node.action.get("tool", ""),
        parameters=node.action.get("params", {}),
        reason="fallback from node plan",
    )
    fallback_validation = validator.validate(fallback_request, budget.remaining)
    if fallback_validation.valid:
        bus.emit(event_bus.AgentDecided, {
            "node_id": node.id, "source": "node_plan",
            "tool": fallback_request.tool, "reason": fallback_request.reason,
            # Same reason as the agent path above: name the actual subject.
            "params": fallback_validation.sanitised_params,
        })
        return {"tool": fallback_request.tool, "params": fallback_validation.sanitised_params}

    bus.emit(event_bus.ToolRejected, {
        "node_id": node.id, "tool": fallback_request.tool, "reason": fallback_validation.reason,
        "params": fallback_request.parameters,
    })
    log.error("Fallback node action also failed validation for node %s: %s",
              node.id, fallback_validation.reason)
    return None


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
    try:
        assessment = verifier.assess(claims_payload, inv.id)
    except Exception as exc:  # noqa: BLE001 — verifier failure is non-fatal (invariant 4)
        log.warning("Verifier agent failed: %s — continuing without assessment", exc)
        return

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
            new_nodes = planner.next_nodes(context)
            added = 0
            for n in new_nodes:
                if _already_scheduled(graph, completed_ids or set(), n):
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
        data = obs.payload.get("data") or {}
        if data.get("url"):
            url = data["url"]
        if data.get("controls"):
            controls = data["controls"]
        if data.get("page_fingerprint"):
            fingerprint = data["page_fingerprint"]
        selector = data.get("selector")
        if selector and (data.get("clicked") or data.get("typed")):
            acted.setdefault(selector, None)
    return {
        "page_url": url,
        "page_controls": controls,
        "page_fingerprint": fingerprint,
        "interacted_selectors": list(acted),
    }


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
