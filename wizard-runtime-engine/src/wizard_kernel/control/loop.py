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

import logging
import uuid
from typing import TYPE_CHECKING

from wizard_kernel.belief import extractors
from wizard_kernel.belief.evidence import EvidenceEngine
from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.belief.trust import source_tier_for_tool
from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.node import InvestigationNode
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.context.engine import ContextEngine
from wizard_kernel.control import hypothesis as hyp_eval
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.control.investigation_graph import InvestigationGraph
from wizard_kernel.control.priority import next_ready
from wizard_kernel.control.tool_validator import ToolRequestValidator
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
    goals = GoalEngine(inv.id)
    obs_store = ObservationStore(inv.id)
    budget = BudgetManager(inv.budget_remaining)
    validator = ToolRequestValidator(inv.repository_path)
    completed_ids: set[str] = set()

    # Context Engine: read-only projection of state into agent context (invariant 3).
    # Its token budget is the LLM context window (distinct from the tool-call
    # `budget` above); the window size is configurable per investigation.
    context_engine = ContextEngine(
        bus, max_context_tokens=inv.options.get("max_context_tokens", 8192)
    )

    sandbox_mode = inv.options.get("sandbox_mode", "local_dev")
    sandbox = get_sandbox(sandbox_mode)

    from wizard_kernel.ports.agents import get_agents
    explorer, verifier = get_agents(inv.options)

    try:
        sandbox.start(inv.repository_path)
        tools = ToolExecutor(sandbox, inv.repository_path)
        _run_loop(inv, manager, planner, explorer, verifier, kg, ev_engine, graph, goals,
                  obs_store, tools, budget, bus, validator, completed_ids, context_engine)
    except Exception as exc:  # noqa: BLE001
        manager.update(inv.id, state=LifecycleState.failed,
                       last_event=f"fatal: {exc}", error=str(exc))
    finally:
        sandbox.stop()


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
    plan = planner.initial(manifest, inv.intent, inv.targets)
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
            new_nodes = planner.next_nodes({
                "investigation_id": inv.id,
                "reason": "need_more_work",
                "kg_summary": kg.summary(),
                "missing_evidence": _missing_evidence_list(goals, kg),
            })
            if not new_nodes:
                break
            for n in new_nodes:
                graph.add(n)
            continue

        graph.set_state(node.id, "running")
        manager.update(inv.id, last_event=f"executing {node.id} ({node.type})")

        # ── Phase 6: Explorer Agent determines HOW to execute this node ───────
        # Context Engine builds the trust-stripped packet (agent contract) plus the
        # modular section view that drives KV-cache ordering + audit (invariant 3).
        ctx = context_engine.build_context("explorer", inv, node, goals, kg, budget, obs_store)
        tool_action = _resolve_tool_action(node, explorer, ctx.packet, validator, budget)

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

        if goals.all_satisfied():
            break

        # ── Phase 6: Periodic Verifier Agent consultation ─────────────────────
        # The Verifier reviews claims but has NO authority to modify trust or goals.
        # The Runtime independently decides how to respond to its assessment.
        if nodes_since_last_verify >= _VERIFIER_INTERVAL:
            nodes_since_last_verify = 0
            _consult_verifier(inv, verifier, kg, goals, graph, planner)

    if budget.is_exhausted():
        bus.emit(event_bus.BudgetExhausted, {"used": budget.used, "total": budget.total})

    # ── Report ────────────────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.reporting, last_event="generating report")
    graph.persist()
    kg.persist()
    goals.persist()

    from wizard_kernel.control.report import generate
    report_md = generate(inv, graph, obs_store.all(), kg, goals)
    fs_store.write_text(inv.id, "verification_report.md", report_md)
    bus.emit(event_bus.ReportGenerated,
             {"path": f".wizard/investigations/{inv.id}/verification_report.md"})

    manager.update(inv.id, state=LifecycleState.completed,
                   last_event="complete", active_goals=goals.to_api_list())


# ── Phase 6 helpers ───────────────────────────────────────────────────────────

def _resolve_tool_action(
    node: InvestigationNode,
    explorer: "ExplorerPort",
    context: dict,
    validator: ToolRequestValidator,
    budget: BudgetManager,
) -> dict | None:
    """Ask the Explorer Agent for a ToolRequest and validate it deterministically.

    Returns the sanitised action dict on success, None on validation failure.
    Falls back to the node's own action if the agent fails or returns an invalid request.
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
            # Use agent's suggested tool with sanitised parameters
            return {"tool": agent_request.tool, "params": validation.sanitised_params}
        else:
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
        return {"tool": fallback_request.tool, "params": fallback_validation.sanitised_params}

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
) -> None:
    """Ask the Verifier Agent to review current claims.

    The Runtime reads the Verifier's assessment and independently decides
    whether to act. The Verifier CANNOT set trust, mark goals, or modify graphs.
    """
    claims_payload = [
        {
            "claim_id": c.id,
            "type": c.claim_type,
            "key": c.key,
            "value": str(c.value),
            # No raw trust scores exposed to agent (invariant 3)
        }
        for c in kg.all_claims()
    ]

    if not claims_payload:
        return  # Nothing to review yet

    try:
        assessment = verifier.assess(claims_payload)
    except Exception as exc:  # noqa: BLE001 — verifier failure is non-fatal (invariant 4)
        log.warning("Verifier agent failed: %s — continuing without assessment", exc)
        return

    log.info("Verifier assessment for %s: %s, weak_claims=%s",
             inv.id, assessment.assessment, assessment.weak_claims)

    # Runtime-only decision: if the Verifier thinks we need more work AND
    # there are weak claims, ask the Planner to generate additional investigation nodes.
    # The Verifier's opinion is advisory. The Runtime independently judges the situation.
    if (assessment.assessment == "needs_more_work"
            and assessment.recommended_additional_investigations):
        context = {
            "investigation_id": inv.id,
            "reason": "verifier_identified_gaps",
            "kg_summary": kg.summary(),
            "missing_evidence": assessment.recommended_additional_investigations,
            "weak_claims": assessment.weak_claims,
        }
        try:
            new_nodes = planner.next_nodes(context)
            for n in new_nodes:
                graph.add(n)
            if new_nodes:
                log.info("Planner added %d nodes based on Verifier assessment for %s",
                         len(new_nodes), inv.id)
        except Exception as exc:  # noqa: BLE001
            log.warning("Planner failed to generate nodes from Verifier assessment: %s", exc)


def _missing_evidence_list(goals: GoalEngine, kg: KnowledgeGraph) -> list[str]:
    """Produce a structured list of what evidence is still missing for open goals."""
    missing = []
    for g in goals.open_goals():
        for claim_type in g.required_claim_types:
            claims = kg.find(claim_type, None)
            if not claims:
                missing.append(f"No claims of type {claim_type!r} for goal {g.name!r}")
            elif g.requires_execution_evidence:
                # Check if any claim has execution-tier evidence
                has_exec = any(
                    any(ev.source_tier == "execution" for ev in kg.evidence_for(c.id))
                    for c in claims
                )
                if not has_exec:
                    missing.append(
                        f"Goal {g.name!r}: {claim_type!r} exists but lacks execution evidence"
                    )
    return missing


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_execute(tools: ToolExecutor, action: dict) -> dict:
    """Invariant 4: any exception becomes an error payload, never a crash."""
    try:
        return tools.execute(action)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "exit_code": -1, "error": str(exc)}
