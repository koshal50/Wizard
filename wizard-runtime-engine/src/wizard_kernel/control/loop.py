"""Main investigation loop — the only algorithm that matters. Phase 3."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from wizard_kernel.contracts.node import InvestigationNode, NodeState
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.control import hypothesis as hyp_eval
from wizard_kernel.control.goals import GoalEngine
from wizard_kernel.control.investigation_graph import InvestigationGraph
from wizard_kernel.control.priority import next_ready
from wizard_kernel.session.investigation import Investigation
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.storage import fs_store

if TYPE_CHECKING:
    from wizard_kernel.ports.planner import PlannerPort


def _obs_id() -> str:
    return f"obs_{uuid.uuid4().hex[:8]}"


def run(
    inv: Investigation,
    manager: InvestigationManager,
    planner: "PlannerPort",
    *,
    tools_executor=None,  # Phase 2: injected tool runner; None = no-op in Phase 3
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
    observations: list[Observation] = []
    completed_ids: set[str] = set()

    # ── Phase: scanning ──────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.scanning, last_event="fast scan started")
    manifest = _fast_scan(inv.repository_path, inv.id)
    fs_store.write(inv.id, "manifest.json", manifest.model_dump())

    # ── Phase: planning ───────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.planning, last_event="initial planner call")
    plan = planner.initial(manifest, inv.intent, inv.targets)
    fs_store.write(inv.id, "plan.json", plan.model_dump())

    for tech in plan.technologies:
        for goal_name in tech.initial_goals:
            from wizard_kernel.control.goals import Goal
            g = Goal(
                id=f"goal_{uuid.uuid4().hex[:6]}",
                name=goal_name,
                required_claim_types=[],
            )
            goals.add(g)

    for node in plan.seed_nodes:
        graph.add(node)

    manager.update(inv.id, state=LifecycleState.investigation_loop,
                   last_event="investigation loop started",
                   active_goals=goals.to_api_list())

    # ── Core loop ─────────────────────────────────────────────────────────────
    obs_seq = 0
    while inv.budget_remaining > 0:
        node = next_ready(graph.all_nodes(), completed_ids)

        if node is None:
            # Ask planner for more nodes
            if not goals.all_satisfied():
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
            break

        graph.set_state(node.id, "running")
        manager.update(inv.id, last_event=f"executing {node.id} ({node.type})")

        # Execute node action
        result_payload = _execute(node, inv.repository_path, tools_executor)

        # Create immutable Observation (invariant 1)
        obs = Observation(
            id=_obs_id(),
            investigation_id=inv.id,
            node_id=node.id,
            source_tool=node.action.get("tool", "unknown"),
            obs_type=_obs_type_for(node),
            payload=result_payload,
            created_at=datetime.now(timezone.utc),
        )
        observations.append(obs)
        obs_seq += 1
        fs_store.write_observation(inv.id, obs_seq, obs.model_dump())

        # Evaluate hypothesis deterministically (invariant 3 — no LLM for expected outcomes)
        match_result = hyp_eval.evaluate(node, obs)

        if match_result == "expected_success" and node.on_success:
            _admit_claim(inv.id, node, obs, "success", fs_store)
            manager.update(inv.id, claims_count=inv.claims_count + 1)
        elif match_result == "expected_failure" and node.on_failure:
            _admit_claim(inv.id, node, obs, "failure", fs_store)
            manager.update(inv.id, claims_count=inv.claims_count + 1)
        else:
            # Unexpected — escalate to Planner (never invent)
            new_nodes = planner.interpret(node, obs)
            for n in new_nodes:
                graph.add(n)

        graph.set_state(node.id, "complete", obs_ids=[obs.id])
        completed_ids.add(node.id)
        manager.update(inv.id,
                       budget_remaining=inv.budget_remaining - 1,
                       nodes_completed=inv.nodes_completed + 1,
                       active_goals=goals.to_api_list())

        # Check checkpoint nodes
        for n in graph.checkpoint_nodes():
            if n.id not in completed_ids:
                graph.set_state(n.id, "complete")
                completed_ids.add(n.id)
                if n.goal_id:
                    goals.mark_satisfied(n.goal_id)

        if goals.all_satisfied():
            break

    # ── Phase: reporting ──────────────────────────────────────────────────────
    manager.update(inv.id, state=LifecycleState.reporting, last_event="generating report")
    graph.persist()

    from wizard_kernel.control.report import generate
    report_md = generate(inv, graph, observations)
    fs_store.write(inv.id, "verification_report.md", {"markdown": report_md})

    manager.update(inv.id, state=LifecycleState.completed,
                   last_event="investigation complete",
                   active_goals=goals.to_api_list())


# ── Helpers (no technology knowledge allowed here) ────────────────────────────

def _fast_scan(repo_path: str, inv_id: str):
    """Delegate to world.scanner — Phase 2 will fully implement this."""
    try:
        from wizard_kernel.world.scanner import scan
        return scan(repo_path, inv_id)
    except (ImportError, AttributeError):
        # Phase 1/3 fallback — minimal manifest so loop can proceed
        from wizard_kernel.contracts.manifest import RepositoryManifest
        return RepositoryManifest(
            investigation_id=inv_id,
            root_path=repo_path,
            total_files=0,
            total_dirs=0,
            key_files=[],
            extensions={},
            directory_tree=[],
            size_bytes_approx=0,
        )


def _execute(node: InvestigationNode, repo_path: str, tools_executor) -> dict:
    """Run the node action; failures become payload, never crashes (invariant 4)."""
    if tools_executor is None:
        return {"exit_code": 0, "stdout": "", "stderr": "", "note": "no-op executor"}
    try:
        return tools_executor(node.action, repo_path)
    except Exception as exc:  # noqa: BLE001
        return {"exit_code": -1, "error": str(exc)}


def _obs_type_for(node: InvestigationNode) -> str:
    tool = node.action.get("tool", "")
    mapping = {
        "read_file": "file_content",
        "list_tree": "filesystem",
        "execute_command": "command_result",
        "search_files": "search_hits",
        "check_port": "port_check",
        "path_exists": "path_check",
    }
    return mapping.get(tool, "command_result")


def _admit_claim(inv_id: str, node: InvestigationNode, obs: Observation,
                 outcome: str, store) -> None:
    """Phase 3 stub — write claim+evidence JSON to disk. Phase 4 wires real KG."""
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
    existing = store.read(inv_id, "claims.json") or []
    existing.append(claim)
    store.write(inv_id, "claims.json", existing)
