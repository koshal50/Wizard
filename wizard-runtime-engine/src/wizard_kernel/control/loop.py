"""Main investigation loop — the only algorithm that matters."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from wizard_kernel.contracts.node import InvestigationNode
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.control import hypothesis as hyp_eval
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.control.investigation_graph import InvestigationGraph
from wizard_kernel.control.priority import next_ready
from wizard_kernel.reality.observations import ObservationStore
from wizard_kernel.session.investigation import Investigation
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store
from wizard_kernel.world import scanner
from wizard_kernel.world.sandbox import get_sandbox
from wizard_kernel.world.tools import ToolExecutor

if TYPE_CHECKING:
    from wizard_kernel.ports.planner import PlannerPort

_TOOL_TO_OBS_TYPE: dict[str, str] = {
    "read_file": "file_content",
    "list_tree": "filesystem",
    "execute_command": "command_result",
    "search_files": "search_hits",
    "check_port": "port_check",
    "path_exists": "path_check",
}


def run(
    inv: Investigation,
    manager: InvestigationManager,
    planner: "PlannerPort",
) -> None:
    """
    Core loop. Invariants (never violate):
    1. Observations immutable after creation.
    2. Claims enter only through evidence.
    3. Planner/Agents never write graphs or trust.
    4. Tool failures → Observations, not crashes.
    5. No technology-specific meaning in Kernel core.
    6. Investigations never share state.
    7. Budget always terminates.
    """
    graph = InvestigationGraph(inv.id)
    goals = GoalEngine()
    obs_store = ObservationStore(inv.id)
    completed_ids: set[str] = set()

    # ── Sandbox setup ─────────────────────────────────────────────────────────
    sandbox_mode = inv.options.get("sandbox_mode", "local_dev")
    sandbox = get_sandbox(sandbox_mode)
    tools = ToolExecutor(sandbox, inv.repository_path)

    try:
        sandbox.start(inv.repository_path)
        _run_loop(inv, manager, planner, graph, goals, obs_store, tools, completed_ids)
    except Exception as exc:  # noqa: BLE001
        manager.update(inv.id, state=LifecycleState.failed,
                       last_event=f"fatal: {exc}", error=str(exc))
        return
    finally:
        sandbox.stop()


def _run_loop(
    inv: Investigation,
    manager: InvestigationManager,
    planner: "PlannerPort",
    graph: InvestigationGraph,
    goals: GoalEngine,
    obs_store: ObservationStore,
    tools: ToolExecutor,
    completed_ids: set[str],
) -> None:
    # ── Scanning ──────────────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.scanning, last_event="fast scan started")
    manifest = scanner.scan(inv.repository_path, inv.id)
    fs_store.write(inv.id, "manifest.json", manifest.model_dump())

    # ── Planning ──────────────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.planning, last_event="initial planner call")
    plan = planner.initial(manifest, inv.intent, inv.targets)
    fs_store.write(inv.id, "plan.json", plan.model_dump())

    for tech in plan.technologies:
        for goal_name in tech.initial_goals:
            goals.add(Goal(
                id=f"goal_{uuid.uuid4().hex[:6]}",
                name=goal_name,
                required_claim_types=[],
            ))

    for node in plan.seed_nodes:
        graph.add(node)

    manager.update(inv.id, state=LifecycleState.investigation_loop,
                   last_event="loop started", active_goals=goals.to_api_list())

    # ── Core loop ─────────────────────────────────────────────────────────────
    while inv.budget_remaining > 0:
        node = next_ready(graph.all_nodes(), completed_ids)

        if node is None:
            if goals.all_satisfied():
                break
            new_nodes = planner.next_nodes({
                "investigation_id": inv.id,
                "reason": "need_more_work",
                "missing_evidence": [],
                "recent_nodes": [],
            })
            if not new_nodes:
                break
            for n in new_nodes:
                graph.add(n)
            continue

        graph.set_state(node.id, "running")
        manager.update(inv.id, last_event=f"executing {node.id} ({node.type})")

        # Execute — failures become observations, never crashes (invariant 4)
        payload = _safe_execute(tools, node)

        # Immutable observation (invariant 1)
        obs = obs_store.append(
            node_id=node.id,
            source_tool=node.action.get("tool", "unknown"),
            obs_type=_TOOL_TO_OBS_TYPE.get(node.action.get("tool", ""), "command_result"),
            payload=payload,
        )

        # Deterministic hypothesis evaluation — no LLM for expected outcomes
        match hyp_eval.evaluate(node, obs):
            case "expected_success" if node.on_success:
                _admit_claim(inv.id, node, obs, "success")
                manager.update(inv.id, claims_count=inv.claims_count + 1)
            case "expected_failure" if node.on_failure:
                _admit_claim(inv.id, node, obs, "failure")
                manager.update(inv.id, claims_count=inv.claims_count + 1)
            case _:
                # Unexpected — escalate to Planner (invariant 3: never invent)
                for n in planner.interpret(node, obs):
                    graph.add(n)

        graph.set_state(node.id, "complete", obs_ids=[obs.id])
        completed_ids.add(node.id)
        manager.update(
            inv.id,
            budget_remaining=inv.budget_remaining - 1,
            nodes_completed=inv.nodes_completed + 1,
            active_goals=goals.to_api_list(),
        )

        # Evaluate checkpoint nodes
        for ckpt in graph.checkpoint_nodes():
            if ckpt.id not in completed_ids:
                graph.set_state(ckpt.id, "complete")
                completed_ids.add(ckpt.id)
                if ckpt.goal_id:
                    goals.mark_satisfied(ckpt.goal_id)

        if goals.all_satisfied():
            break

    # ── Report ────────────────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.reporting, last_event="generating report")
    graph.persist()

    from wizard_kernel.control.report import generate
    report_md = generate(inv, graph, obs_store.all())
    fs_store.write(inv.id, "verification_report.md", {"markdown": report_md})

    manager.update(inv.id, state=LifecycleState.completed,
                   last_event="complete", active_goals=goals.to_api_list())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_execute(tools: ToolExecutor, node: InvestigationNode) -> dict:
    """Invariant 4: any exception becomes an error payload, never a crash."""
    try:
        return tools.execute(node.action)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "exit_code": -1, "error": str(exc)}


def _admit_claim(inv_id: str, node: InvestigationNode, obs, outcome: str) -> None:
    """Write claim + evidence to disk. Phase 4 wires the real Knowledge Graph."""
    template = node.on_success if outcome == "success" else node.on_failure
    if not template:
        return
    claim = {
        "id": f"cl_{uuid.uuid4().hex[:8]}",
        "investigation_id": inv_id,
        "claim_type": template.claim_type,
        "key": template.key,
        "value": template.value,
        "node_id": node.id,
        "observation_id": obs.id,
        "source": "hypothesis_match",
    }
    existing = fs_store.read(inv_id, "claims.json") or []
    existing.append(claim)
    fs_store.write(inv_id, "claims.json", existing)
