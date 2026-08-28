"""
Example end-to-end workflow demonstrating the full documented flow:

    Planner/Runtime -> Explorer Input -> Explorer Output
        -> Runtime Tool Execution -> Observation -> Claims Graph
        -> Verification Input -> Verification Output
        -> Runtime -> verification_report.md

This runs entirely offline using MockLLMProvider and MockRuntimeExecutor,
so it works with zero configuration and no API key.

Run with:
    python examples/end_to_end_example.py
"""
from __future__ import annotations

from pathlib import Path

from app.adapters.mock_runtime import MockRuntimeExecutor
from app.contracts.common import RepositoryMetadata
from app.contracts.explorer import ExplorerInput, InvestigationNode, Route
from app.contracts.verification import ClaimInput, EvidenceInput, EvidenceSource, VerificationInput
from app.explorer.agent import ExplorerAgent
from app.llm.mock_provider import MockLLMProvider
from app.verification.agent import VerificationAgent


def main() -> None:
    llm = MockLLMProvider()
    explorer = ExplorerAgent(llm)
    verifier = VerificationAgent(llm)
    runtime = MockRuntimeExecutor()

    # 1. Investigation Planner (simulated) hands Explorer a node + route.
    node = InvestigationNode(
        node_id="identify_application_entrypoint",
        goal="Determine which file is the application entrypoint",
    )
    route = Route(node_order=[node.node_id, "inspect_dependencies"], current_index=0)
    explorer_input = ExplorerInput(
        investigation_id="inv-example-001",
        current_node=node,
        route=route,
        nodes=[node, InvestigationNode(node_id="inspect_dependencies", goal="List dependencies")],
        active_goals=["Understand how the application starts"],
        repository_metadata=RepositoryMetadata(
            root_path="/repo", detected_languages=["python"], detected_frameworks=["fastapi"]
        ),
    )
    print("=== 1. Explorer Input ===")
    print(explorer_input.model_dump_json(indent=2))

    # 2. Explorer reasons and produces a validated Tool Request / plan.
    explorer_output = explorer.investigate(explorer_input)
    print("\n=== 2. Explorer Output (Tool Request / Plan) ===")
    print(explorer_output.model_dump_json(indent=2))

    # 3. Runtime executes the tool request (mocked here; real Runtime
    #    Engine is a separate subsystem built by another developer).
    tool_request = explorer_output.to_tool_request()
    observation = runtime.execute(tool_request)
    print("\n=== 3. Observation (from Runtime, mocked) ===")
    print(observation)

    # 4. Runtime builds/updates the Claims Graph from the Observation.
    claim = ClaimInput(
        claim_id="claim-entrypoint",
        statement="The application entrypoint is main.py, launched via `python main.py`",
        node_id=explorer_output.node_id,
        evidence=[
            EvidenceInput(
                evidence_id="ev-1",
                description=f"Runtime observation from {tool_request.tool.value}: {observation['data']}",
                source=EvidenceSource.EXECUTION,
                supports_claim=True,
                node_id=explorer_output.node_id,
            )
        ],
    )

    # 5. Claims Graph info flows into Verification.
    verification_input = VerificationInput(
        investigation_id=explorer_input.investigation_id,
        claims=[claim],
        relevant_goals=explorer_input.active_goals,
    )
    verification_output = verifier.verify(verification_input)
    print("\n=== 4. Verification Output ===")
    print(verification_output.model_dump_json(indent=2))

    # 6. Runtime writes the authoritative verification_report.md.
    out_path = Path(__file__).parent / "verification_report.md"
    out_path.write_text(verification_output.report_markdown, encoding="utf-8")
    print(f"\n=== 5. Wrote report to {out_path} ===")


if __name__ == "__main__":
    main()
