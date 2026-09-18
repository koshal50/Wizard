"""Phase 3 probe — the kernel's agent seam, against the live Agent System.

Sends the kernel's own context packet (built by the Context Engine's packager,
not hand-written) to the agent service's /agent/explorer adapter, then validates
the reply against the kernel's ExplorerResponse contract. Same for the verifier.

The agent service runs its deterministic `mock` LLM provider — no model, no key,
no network. Everything here is real HTTP between the two services.
"""
import json
import sys

import httpx

from wizard_kernel.belief.evidence import EvidenceEngine
from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.contracts.agent import ExplorerResponse, VerifierAssessment
from wizard_kernel.contracts.node import InvestigationNode
from wizard_kernel.context.packager import Packager
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.ports.agents import HttpExplorer, HttpVerifier
from wizard_kernel.session.budget import BudgetManager
from wizard_kernel.session.investigation import Investigation

AGENTS = "http://127.0.0.1:8100"
REPO = "F:/Shivam/finalyear_project/wizard/wizard-runtime-engine"


def hr(t):
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


inv = Investigation(id="inv_probe3", repository_path=REPO, intent="investigate",
                    targets=[], options={})
goals = GoalEngine("inv_probe3")
goals.add(Goal(id="goal_0", name="Verify Runtime", required_claim_types=["RUNTIME"],
               requires_execution_evidence=True))
kg = KnowledgeGraph("inv_probe3")

# ── 1. A real node, and the kernel's real packet for it ──────────────────────
node = InvestigationNode(
    id="node_read1", type="read",
    action={"tool": "read_file", "params": {"path": "pyproject.toml", "max_bytes": 65536}},
    hypothesis={"kind": "always_success"},
    goal_id="goal_0",
)
packet = Packager().build_explorer_packet(inv, node, goals, kg, BudgetManager(12))
hr("1. KERNEL PACKET (Context Engine packager)")
print(json.dumps(packet, indent=2))

# ── 2. POST it to the adapter exactly as HttpExplorer does ───────────────────
hr("2. POST /agent/explorer")
raw = httpx.post(f"{AGENTS}/agent/explorer", json=packet, timeout=30)
print("status:", raw.status_code)
print(json.dumps(raw.json(), indent=2))

hr("3. KERNEL-SIDE VALIDATION (ExplorerResponse)")
resp = ExplorerResponse.model_validate(raw.json())
print("tool      :", resp.tool_request.tool)
print("parameters:", resp.tool_request.parameters)
print("reason    :", resp.tool_request.reason)

# ── 4. Would the kernel's validator accept it? ───────────────────────────────
from wizard_kernel.control.tool_validator import ToolRequestValidator
v = ToolRequestValidator(REPO)
result = v.validate(resp.tool_request, budget_remaining=12)
print(f"\nvalidator : valid={result.valid} reason={result.reason!r}")
print(f"sanitised : {result.sanitised_params}")

# ── 5. The HTTP port itself, end to end ──────────────────────────────────────
hr("4. HttpExplorer (the port the kernel actually uses)")
via_port = HttpExplorer(f"{AGENTS}/agent/explorer").request(packet)
print("tool      :", via_port.tool_request.tool)
print("parameters:", via_port.tool_request.parameters)

# ── 6. Verifier ──────────────────────────────────────────────────────────────
hr("5. VERIFIER SEAM")
store_obs = None
claims_payload = []
kg2 = KnowledgeGraph("inv_probe3")
ev = EvidenceEngine(kg2)
from wizard_kernel.reality.observations import ObservationStore
store = ObservationStore("inv_probe3")
o1 = store.append(node_id="n1", source_tool="execute_command", obs_type="command_result",
                  payload={"ok": True, "data": {"exit_code": 0}})
ev.admit(inv_id="inv_probe3", claim_type="RUNTIME", key="python --version",
         value="verified", obs_id=o1.id, support_type="support",
         source_tier="execution", node_id="n1")
o2 = store.append(node_id="n2", source_tool="read_file", obs_type="file_content",
                  payload={"ok": True, "data": {"content": "x"}})
ev.admit(inv_id="inv_probe3", claim_type="PACKAGE", key="name", value="wizard",
         obs_id=o2.id, support_type="support", source_tier="config_parse", node_id="n2")

claims_payload = [
    {
        "claim_id": c.id, "type": c.claim_type, "key": c.key, "value": str(c.value),
        # Provenance, as the kernel's _consult_verifier now sends it.
        "evidence": [
            {"evidence_id": ev.id, "source_tier": ev.source_tier,
             "support_type": ev.support_type}
            for ev in kg2.evidence_for(c.id)
        ],
    }
    for c in kg2.all_claims()
]
print("claims sent:", json.dumps(claims_payload, indent=2))

rawv = httpx.post(f"{AGENTS}/agent/verifier",
                  json={"investigation_id": "inv_probe3", "claims": claims_payload},
                  timeout=30)
print("\nstatus:", rawv.status_code)
print(json.dumps(rawv.json(), indent=2))

assess = VerifierAssessment.model_validate(rawv.json())
print(f"\nVERDICT: assessment={assess.assessment!r} weak={assess.weak_claims}")
print(f"recommended={assess.recommended_additional_investigations}")
assert assess.investigation_id == "inv_probe3", "kernel id must survive the round trip"

via_port_v = HttpVerifier(f"{AGENTS}/agent/verifier").assess(claims_payload, "inv_probe3")
print(f"\nHttpVerifier: assessment={via_port_v.assessment!r} "
      f"investigation_id={via_port_v.investigation_id!r}")

ok = result.valid and via_port.tool_request.tool == "read_file"
print(f"\n{'PASS' if ok else 'FAIL'}: explorer proposal accepted by the kernel's validator")
sys.exit(0 if ok else 1)
