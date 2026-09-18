"""Phase 2 probe — drive the REAL kernel<->planner seam and print every hop.

Builds the manifest with the kernel's own scanner, calls /plan/initial, then
builds the /plan/next packet exactly as control/loop._planner_next_context does
and prints what comes back. Nothing here is a mock: real scanner, real HTTP,
real planner service, deterministic heuristic provider.
"""
import json
import sys

import httpx

from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.control import loop
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.contracts.plan import TechnologyPlan
from wizard_kernel.reality.observations import ObservationStore
from wizard_kernel.session.budget import BudgetManager
from wizard_kernel.session.investigation import Investigation
from wizard_kernel.world import scanner

REPO = "F:/Shivam/finalyear_project/wizard/wizard-runtime-engine"
PLANNER = "http://127.0.0.1:8787"


def hr(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


# ── 1. Manifest (real kernel scanner) ────────────────────────────────────────
manifest = scanner.scan(REPO, "inv_probe")
hr("1. MANIFEST (kernel scanner)")
print(f"files={manifest.total_files} dirs={manifest.total_dirs}")
print(f"key_files={manifest.key_files}")

# ── 2. /plan/initial ─────────────────────────────────────────────────────────
hr("2. POST /plan/initial")
resp = httpx.post(f"{PLANNER}/plan/initial", json={
    "manifest": manifest.model_dump(mode="json"),
    "intent": "investigate",
    "targets": [],
}, timeout=30)
print("status:", resp.status_code)
plan_wire = resp.json()
print(json.dumps(plan_wire, indent=2)[:1500])
plan = TechnologyPlan.model_validate(plan_wire)

# ── 3. Goals the kernel would create from that plan ──────────────────────────
goals = GoalEngine("inv_probe")
for tech in plan.technologies:
    for gd in tech.initial_goals:
        goals.add(Goal(
            id=f"goal_{len(goals.all())}",
            name=gd.name,
            required_claim_types=list(gd.required_claim_types),
            belief_threshold=gd.belief_threshold,
            requires_execution_evidence=gd.requires_execution_evidence,
        ))
hr("3. GOALS created from the plan")
for g in goals.all():
    print(f"  {g.name!r:24} claim_types={g.required_claim_types} "
          f"exec_required={g.requires_execution_evidence}")

# ── 4. The /plan/next packet, built by the kernel's own helper ───────────────
inv = Investigation(id="inv_probe", repository_path=REPO,
                    intent="investigate", targets=[], options={})
kg = KnowledgeGraph("inv_probe")
budget = BudgetManager(14)
# The observation store is part of the packet now: the planner needs to know
# which files have already been read (and parsed) so it does not spend budget
# re-proposing them. An empty store here — nothing has been read yet.
obs_store = ObservationStore("inv_probe")
packet = loop._planner_next_context(inv, goals, kg, plan, budget, obs_store, "need_more_work")
hr("4. PACKET from loop._planner_next_context")
print(json.dumps(packet, indent=2)[:1800])

# ── 5. /plan/next ────────────────────────────────────────────────────────────
hr("5. POST /plan/next")
resp = httpx.post(f"{PLANNER}/plan/next", json=packet, timeout=30)
print("status:", resp.status_code)
print(json.dumps(resp.json(), indent=2)[:1800])

# ── 6. Validate the returned nodes against the kernel's own contract ─────────
hr("6. KERNEL-SIDE VALIDATION of returned nodes")
from wizard_kernel.contracts.node import InvestigationNode
raw = resp.json().get("new_nodes", [])
print(f"new_nodes: {len(raw)}")
ok = 0
for n in raw:
    try:
        node = InvestigationNode.model_validate(n)
        ok += 1
        print(f"  OK  {node.type:9} tool={node.action.get('tool')!r} "
              f"params={node.action.get('params')}")
    except Exception as e:
        print(f"  FAIL {json.dumps(n)[:160]}\n       {type(e).__name__}: {e}")
print(f"\n{ok}/{len(raw)} nodes satisfy the kernel's InvestigationNode contract")
sys.exit(0 if raw else 1)
