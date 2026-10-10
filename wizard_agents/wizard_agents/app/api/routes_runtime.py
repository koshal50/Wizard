"""Runtime adapter routes — the seam the Python kernel's agent ports call.

The kernel talks to two agents through `wizard_kernel/ports/agents.py`:

    HttpExplorer.request(context)   POST <agent_explorer_url>  -> ExplorerResponse
    HttpVerifier.assess(claims)     POST <agent_verifier_url>  -> VerifierAssessment

Those wire shapes are the Runtime's, not ours: the kernel POSTs to the URL
verbatim and validates the reply against its own Pydantic contracts
(`contracts/agent.py`). This module is the translation layer — it accepts the
kernel's packet, builds the Agent System's richer `ExplorerInput` /
`VerificationInput`, runs the real agent, and translates the agent's output back
into the minimal shape the kernel consumes.

Keeping the translation here rather than in the kernel means the kernel stays
unaware of our internal contracts (it only ever sees its own), and the agents
stay unaware of the kernel's. Neither subsystem has to import the other.

Mounted at /agent/explorer and /agent/verifier — the paths the kernel is
configured with (InvestigationOptions.agent_explorer_url / agent_verifier_url).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_provider
from app.contracts.common import (
    ExecutionBudget,
    RepositoryMetadata,
    ToolName,
)
from app.contracts.explorer import (
    ExplorerInput,
    InvestigationNode,
    Route,
)
from app.contracts.verification import (
    ClaimInput,
    EvidenceInput,
    EvidenceSource,
    VerificationInput,
)
from app.explorer.agent import ExplorerAgent, ExplorerAgentError
from app.llm.base import LLMProvider
from app.verification.agent import VerificationAgent, VerificationAgentError

router = APIRouter(prefix="/agent", tags=["runtime-adapter"])


# ── Explorer ──────────────────────────────────────────────────────────────────

# The tools the Runtime will actually accept. Sent to Explorer as
# `available_tools`, which app/validation checks the output against — so a
# proposal naming anything else is refused here rather than travelling to the
# kernel only to be rejected as an unknown tool.
RUNTIME_TOOLS: List[ToolName] = [
    ToolName.READ_FILE,
    ToolName.SEARCH_FILES,
    ToolName.LIST_TREE,
    ToolName.PATH_EXISTS,
    ToolName.EXECUTE_COMMAND,
    ToolName.START_PROCESS,
    ToolName.READ_PROCESS,
    ToolName.KILL_PROCESS,
    ToolName.LIST_PROCESSES,
    ToolName.CHECK_PORT,
    ToolName.HTTP_REQUEST,
    ToolName.BROWSER_NAVIGATE,
    ToolName.BROWSER_SNAPSHOT,
    ToolName.BROWSER_CLICK,
    ToolName.BROWSER_TYPE,
    ToolName.BROWSER_BACK,
    ToolName.BROWSER_EXTRACT,
    ToolName.BROWSER_SCREENSHOT,
]

# Kernel node types that imply a tool when the node carries no explicit action.
_NODE_TYPE_TOOL: Dict[str, ToolName] = {
    "read": ToolName.READ_FILE,
    "discovery": ToolName.SEARCH_FILES,
    "execute": ToolName.EXECUTE_COMMAND,
}


def _require(packet: Dict[str, Any], key: str) -> str:
    """Read a required packet field, refusing to invent a value.

    The kernel always sets these, so a blank one means the packet is malformed —
    and a substituted placeholder would make a broken call look like a healthy
    one. Fail here, where the caller can see it, rather than downstream.
    """
    value = packet.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"packet field {key!r} is missing or blank")
    return value


def _goal_text(packet: Dict[str, Any]) -> str:
    """A human-readable goal for the current node.

    The kernel's packet names the node's goal only by id, so resolve it against
    the active goals it sent alongside. Falls back to the node type — never to an
    empty string, which the contract rejects.
    """
    node = packet.get("current_node") or {}
    goal_id = node.get("goal_id")
    active_goals = packet.get("active_goals") or []
    selected = next((g for g in active_goals if goal_id is not None and g.get("id") == goal_id),
                    active_goals[0] if active_goals else None)
    if selected:
        return selected.get("name") or "investigate node"
    if packet.get("targets"):
        return f"investigate {'/'.join(str(t) for t in packet['targets'])}"
    return f"investigate {node.get('type') or 'node'}"


def _to_explorer_input(packet: Dict[str, Any]) -> ExplorerInput:
    """Kernel context packet -> ExplorerInput (app/contracts/explorer.py)."""
    investigation_id = _require(packet, "investigation_id")
    node = packet.get("current_node") or {}
    node_id = _require(node, "id")
    action = node.get("action") or {}

    current = InvestigationNode(
        node_id=node_id,
        goal=_goal_text(packet),
        description=f"type={node.get('type')}",
        planned_action=action or None,
    )

    budget = packet.get("remaining_budget")
    active_goals = packet.get("active_goals") or []
    active_goal = next((g for g in active_goals
                        if node.get("goal_id") is not None
                        and g.get("id") == node.get("goal_id")),
                       active_goals[0] if active_goals else None)
    evidence_context = ""
    missing_evidence: list[str] = []
    if active_goal:
        required = active_goal.get("required_evidence") or []
        completed = active_goal.get("completed_evidence") or []
        missing_evidence = active_goal.get("missing_evidence") or []
        evidence_context = (
            f"\nACTIVE GOAL: {active_goal.get('name', '')}"
            f"\nREQUIRED EVIDENCE: {', '.join(required) or '(none declared)'}"
            f"\nCOMPLETED EVIDENCE: {', '.join(completed) or '(none yet)'}"
            f"\nMISSING EVIDENCE: {', '.join(missing_evidence) or '(none)'}"
        )
    return ExplorerInput(
        investigation_id=investigation_id,
        current_node=current,
        # The kernel sends one node at a time, so the route is that single node.
        # Route requires current_node.node_id to appear in node_order.
        route=Route(node_order=[node_id], current_index=0),
        nodes=[current],
        active_goals=[g.get("name", "") for g in active_goals],
        known_claims=[],
        context=(f"intent={packet.get('intent')} targets={packet.get('targets')}"
                 f"{evidence_context}\nRUNTIME RESOURCE STATE: "
                 f"{json.dumps(packet.get('resource_state') or {}, separators=(',', ':'))}"),
        missing_evidence=missing_evidence,
        previous_actions=packet.get("previous_actions") or [],
        investigation=packet.get('investigation') or {},
        goals=active_goals,
        plan=packet.get('plan') or {},
        node_selection=packet.get('node_selection') or {'valid_node_ids': [node_id]},
        successful_results=packet.get('successful_results') or [],
        recent_failures=packet.get('recent_failures') or [],
        resources=packet.get('resource_state') or {},
        http=packet.get('http') or {},
        available_tools=[
            tool for tool in RUNTIME_TOOLS
            if tool.value in set(packet.get("available_tools") or [])
            and (packet.get("browser_enabled") or not tool.value.startswith("browser_"))
        ],
        repository_metadata=RepositoryMetadata(notes=str(packet.get("kg_summary") or "")),
        execution_budget=ExecutionBudget(
            max_steps=1,
            max_tool_calls=1,
            time_budget_seconds=int(budget) if isinstance(budget, int) and budget > 0 else None,
        ),
    )


def _to_kernel_response(investigation_id: str, output: Any) -> Dict[str, Any]:
    """Convert the one validated Explorer decision to the kernel ToolRequest."""
    if output.decision != 'action':
        return {'investigation_id': investigation_id, 'decision': output.decision,
                'node_id': output.node_id, 'reason': output.reason, 'tool_request': None}
    request = output.to_tool_request()
    params = dict(request.parameters or {})
    if request.command:
        params["command"] = request.command
    return {
        "investigation_id": investigation_id,
        "node_id": output.node_id,
        "tool_request": {
            "tool": request.tool.value,
            "parameters": params,
            "reason": "",
        },
    }


@router.post("/explorer")
def explorer(
    packet: Dict[str, Any], provider: LLMProvider = Depends(get_provider)
) -> Dict[str, Any]:
    try:
        explorer_input = _to_explorer_input(packet)
    except Exception as exc:  # noqa: BLE001 — a malformed packet is the caller's error
        raise HTTPException(status_code=422, detail=f"unusable kernel packet: {exc}") from exc

    try:
        output = ExplorerAgent(provider).investigate(explorer_input)
    except ExplorerAgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _to_kernel_response(explorer_input.investigation_id, output)


# ── Verifier ──────────────────────────────────────────────────────────────────

# The Runtime reports each claim's evidence provenance as `source_tier` — the
# tier names its own evidence store uses. Map them onto this system's vocabulary
# so the Verification agent can weigh a claim by what actually backs it.
#
# The Runtime never sends a trust score (kernel invariant 3: agents never see
# trust); provenance is the part that is legitimately ours to reason about.
_TIER_TO_SOURCE: Dict[str, EvidenceSource] = {
    "execution": EvidenceSource.EXECUTION,
    "config_parse": EvidenceSource.CONFIGURATION,
    "documentation": EvidenceSource.DOCUMENTATION,
}


def _to_verification_input(packet: Dict[str, Any]) -> VerificationInput:
    """Kernel {investigation_id, claims: [...]} -> VerificationInput."""
    investigation_id = _require(packet, "investigation_id")
    claims: List[ClaimInput] = []
    for c in packet.get("claims") or []:
        claim_id = str(c.get("claim_id") or "claim")
        ctype = c.get("type") or "CLAIM"
        key = c.get("key")
        value = c.get("value")
        statement = f"{ctype} {key} = {value}" if key is not None else f"{ctype} = {value}"

        evidence: List[EvidenceInput] = []
        for i, ev in enumerate(c.get("evidence") or []):
            tier = str(ev.get("source_tier") or "")
            supporting = ev.get("support_type") != "contradict"
            evidence.append(
                EvidenceInput(
                    evidence_id=str(ev.get("evidence_id") or f"ev_{claim_id}_{i}"),
                    description=(
                        f"{ev.get('support_type', 'support')} from a "
                        f"{tier or 'unknown'}-tier source; observations: "
                        f"{', '.join(str(oid) for oid in ev.get('observation_ids', [])) or 'not supplied'}"
                    ),
                    source=_TIER_TO_SOURCE.get(tier, EvidenceSource.OTHER),
                    supports_claim=supporting,
                    node_id=ev.get("node_id"),
                )
            )

        claims.append(
            ClaimInput(claim_id=claim_id, statement=statement, evidence=evidence)
        )
    return VerificationInput(
        investigation_id=investigation_id,
        deadline_at=packet.get('deadline_at'),
        claims=claims,
        relevant_goals=[str(g) for g in packet.get("relevant_goals") or packet.get("active_goals") or []],
        context=packet.get('context'),
    )


def _to_kernel_assessment(investigation_id: str, output: Any) -> Dict[str, Any]:
    """VerificationOutput -> the kernel's VerifierAssessment (contracts/agent.py).

    The kernel's contract is much narrower than the agent's: it wants an overall
    verdict plus string lists. "needs_more_work" is derived from the agent's own
    findings rather than from a separate flag — a contradiction, an unresolved
    claim, or a recommendation all mean the Runtime should keep investigating.
    """
    weak_ids = [f.claim_id for f in output.weak_claims]
    contradiction_ids = [f.claim_id for f in output.contradictions]
    unresolved = list(output.unresolved_claims)
    recommended = list(output.recommended_additional_investigations)

    needs_more = bool(contradiction_ids or unresolved or recommended)
    return {
        "investigation_id": investigation_id,
        "assessment": "needs_more_work" if needs_more else "overall_sufficient",
        "weak_claims": weak_ids,
        "recommended_additional_investigations": recommended,
        "report_markdown": output.report_markdown,
    }


@router.post("/verifier")
def verifier(
    packet: Dict[str, Any], provider: LLMProvider = Depends(get_provider)
) -> Dict[str, Any]:
    try:
        verification_input = _to_verification_input(packet)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"unusable kernel packet: {exc}") from exc

    try:
        output = VerificationAgent(provider).verify(verification_input)
    except VerificationAgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _to_kernel_assessment(verification_input.investigation_id, output)
