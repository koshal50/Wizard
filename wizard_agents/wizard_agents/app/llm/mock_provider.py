"""
MockLLMProvider: a deterministic, offline stand-in for a real LLM.

This lets the entire Agent System run end-to-end (including all tests and
examples) with zero external dependencies and no API key. It builds
plausible ExplorerOutput / VerificationOutput objects directly from the
structured input the agent gives it (passed via `metadata["input"]`)
rather than trying to parse free-text prompts.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from app.contracts.common import ExecutionStep, ToolName
from app.contracts.explorer import ExplorerOutput
from app.contracts.verification import Severity, VerificationFinding, VerificationOutput
from app.llm.base import LLMError, LLMProvider

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    """Deterministic mock. Supports ExplorerOutput and VerificationOutput.

    The mock is intentionally "reasonable but simple": it picks the first
    available tool, references the current node, and produces claim
    findings based on simple heuristics over the supplied evidence. It
    exists to make the system runnable/testable without a real LLM, not
    to demonstrate investigative intelligence.
    """

    @property
    def name(self) -> str:
        return "mock"

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        *,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> T:
        metadata = metadata or {}
        raw_input = metadata.get("input")
        if raw_input is None:
            raise LLMError("MockLLMProvider requires metadata['input'] to build a deterministic response")

        if response_model is ExplorerOutput:
            return self._build_explorer_output(raw_input)  # type: ignore[return-value]
        if response_model is VerificationOutput:
            return self._build_verification_output(raw_input)  # type: ignore[return-value]

        raise LLMError(
            f"MockLLMProvider does not know how to build response_model={response_model.__name__}"
        )

    # -- Explorer -----------------------------------------------------

    def _build_explorer_output(self, raw_input: Dict[str, Any]) -> ExplorerOutput:
        node = raw_input["current_node"]
        node_id = node["node_id"]
        goal = node.get("goal", "investigate node")

        available_tools = raw_input.get("available_tools") or [t.value for t in ToolName]

        # A Planner-authored node arrives with the concrete action it was created
        # for. Honour it: the node knows which file or command this step is about,
        # and re-deriving that here would only replace a precise action with a
        # generic one. Overriding would also need a reason the deterministic
        # provider has no basis to invent.
        planned = node.get("planned_action") or {}
        planned_tool = planned.get("tool")
        selected_tool: ToolName
        parameters: Dict[str, Any]
        command = None
        if planned_tool and planned_tool in available_tools:
            selected_tool = ToolName(planned_tool)
            parameters = dict(planned.get("params") or {})
            if selected_tool == ToolName.EXECUTE_COMMAND:
                command = parameters.pop("command", None)
        else:
            selected_tool = (
                ToolName.READ_FILE if ToolName.READ_FILE.value in available_tools
                else ToolName(available_tools[0])
            )
            parameters = {}
            if selected_tool == ToolName.EXECUTE_COMMAND:
                command = "true"
                parameters = {"reason": "mock placeholder command"}
            elif selected_tool == ToolName.READ_FILE:
                parameters = {"path": "."}
            elif selected_tool == ToolName.SEARCH_FILES:
                parameters = {"query": goal}
            elif selected_tool == ToolName.LIST_TREE:
                parameters = {"path": "."}
            elif selected_tool == ToolName.INSPECT_CONFIGURATION:
                parameters = {"target": "default"}
            elif selected_tool == ToolName.TRACE_EXECUTION:
                parameters = {"entrypoint": goal}

        route = raw_input.get("route", {})
        node_order = route.get("node_order", [node_id])
        current_index = route.get("current_index", 0)
        next_node = None
        if current_index + 1 < len(node_order):
            next_node = node_order[current_index + 1]

        # The step's parameters must describe the same call the tool request makes,
        # so re-attach the command that was lifted out of `parameters` above.
        step_parameters = dict(parameters)
        if command is not None:
            step_parameters["command"] = command

        steps = [
            ExecutionStep(
                step_number=1,
                description=f"Use {selected_tool.value} to gather evidence for node '{node_id}'",
                tool=selected_tool,
                parameters=step_parameters,
            )
        ]

        if planned_tool and planned_tool in available_tools:
            reasoning = (
                f"Node '{node_id}' has goal '{goal}' and arrived with a planned action "
                f"'{planned_tool}'. Honoured it: the node was created for this specific "
                f"call, so re-deriving a tool here would only lose precision."
            )
        else:
            reasoning = (
                f"Node '{node_id}' has goal '{goal}' and no usable planned action. "
                f"Selected '{selected_tool.value}' because it is available and directly "
                f"applicable to this goal."
            )

        return ExplorerOutput(
            investigation_id=raw_input["investigation_id"],
            node_id=node_id,
            purpose=f"Establish evidence toward goal: {goal}",
            reasoning=reasoning,
            selected_tool=selected_tool,
            parameters=parameters,
            command=command,
            execution_steps=steps,
            expected_observation=f"Evidence relevant to: {goal}",
            success_condition=f"Runtime returns data addressing: {goal}",
            failure_condition="Tool execution fails, times out, or returns no relevant data",
            next_node=next_node,
            fallback="Escalate to Planner for an alternate node or tool if this plan fails",
        )

    # -- Verification ---------------------------------------------------

    def _build_verification_output(self, raw_input: Dict[str, Any]) -> VerificationOutput:
        claims = raw_input["claims"]
        investigation_id = raw_input["investigation_id"]

        supported_claims = []
        weak_claims = []
        contradictions = []
        unresolved_claims = []
        missing_evidence = []
        reviewed_claims = []

        for claim in claims:
            claim_id = claim["claim_id"]
            reviewed_claims.append(claim_id)
            evidence = claim.get("evidence", [])
            supporting = [e for e in evidence if e.get("supports_claim", True)]
            contradicting = [e for e in evidence if not e.get("supports_claim", True)]
            has_execution_evidence = any(e.get("source") == "execution" for e in evidence)

            if contradicting:
                contradictions.append(
                    VerificationFinding(
                        claim_id=claim_id,
                        finding="Claim has contradictory evidence",
                        severity=Severity.HIGH,
                        rationale=(
                            f"{len(contradicting)} piece(s) of evidence contradict this claim "
                            f"while {len(supporting)} support it."
                        ),
                    )
                )
                unresolved_claims.append(claim_id)
            elif not evidence:
                missing_evidence.append(f"No evidence supplied for claim '{claim_id}'")
                unresolved_claims.append(claim_id)
            elif not has_execution_evidence:
                weak_claims.append(
                    VerificationFinding(
                        claim_id=claim_id,
                        finding="Claim is supported only by documentation/static evidence",
                        severity=Severity.MEDIUM,
                        rationale="No execution-based evidence was found for this claim.",
                    )
                )
            else:
                supported_claims.append(claim_id)

        overall = (
            f"{len(supported_claims)}/{len(claims)} claim(s) well-supported, "
            f"{len(weak_claims)} weak, {len(contradictions)} contradicted, "
            f"{len(unresolved_claims)} unresolved."
        )

        recommended = []
        for c in weak_claims:
            recommended.append(f"Gather execution evidence for claim '{c.claim_id}'")
        for c in contradictions:
            recommended.append(f"Re-investigate claim '{c.claim_id}' to resolve contradictory evidence")

        report_lines = [
            f"# Verification Report — {investigation_id}",
            "",
            "## Overall Assessment",
            overall,
            "",
            "## Supported Claims",
        ]
        report_lines += [f"- {c}" for c in supported_claims] or ["- None"]
        report_lines += ["", "## Weak Claims"]
        report_lines += [f"- `{c.claim_id}`: {c.finding} — {c.rationale}" for c in weak_claims] or ["- None"]
        report_lines += ["", "## Contradictions"]
        report_lines += [f"- `{c.claim_id}`: {c.finding} — {c.rationale}" for c in contradictions] or ["- None"]
        report_lines += ["", "## Missing Evidence"]
        report_lines += [f"- {m}" for m in missing_evidence] or ["- None"]
        report_lines += ["", "## Recommended Additional Investigation"]
        report_lines += [f"- {r}" for r in recommended] or ["- None"]
        report_markdown = "\n".join(report_lines) + "\n"

        return VerificationOutput(
            investigation_id=investigation_id,
            overall_assessment=overall,
            reviewed_claims=reviewed_claims,
            supported_claims=supported_claims,
            weak_claims=weak_claims,
            contradictions=contradictions,
            missing_evidence=missing_evidence,
            unresolved_claims=unresolved_claims,
            recommended_additional_investigations=recommended,
            reasoning=(
                "Applied deterministic heuristics: claims with contradicting evidence are flagged as "
                "contradictions; claims with no evidence are flagged missing; claims with only "
                "non-execution evidence are flagged weak; all else supported."
            ),
            report_markdown=report_markdown,
        )
