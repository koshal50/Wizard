from __future__ import annotations

from app.adapters.mock_runtime import MockRuntimeExecutor
from app.contracts.verification import ClaimInput, EvidenceInput, EvidenceSource, VerificationInput
from app.explorer.agent import ExplorerAgent
from app.llm.mock_provider import MockLLMProvider
from app.verification.agent import VerificationAgent
from tests.fixtures.contradictory_documentation_project import (
    build_contradictory_documentation_verification_input,
)
from tests.fixtures.failed_execution_project import (
    build_failed_execution_explorer_input,
    build_failed_execution_verification_input,
)
from tests.fixtures.missing_dependency_project import build_missing_dependency_explorer_input
from tests.fixtures.nodejs_project import build_nodejs_project_explorer_input
from tests.fixtures.python_project import build_python_project_explorer_input


def test_full_pipeline_planner_to_verification():
    """Simulates the whole documented flow:

    Planner-like input -> Explorer -> Tool Request -> Mock Runtime ->
    Observation -> Claims -> Verification -> Assessment
    """
    llm = MockLLMProvider()
    explorer = ExplorerAgent(llm)
    verifier = VerificationAgent(llm)
    runtime = MockRuntimeExecutor()

    # 1. Planner supplies a node + route (simulated here via fixture).
    explorer_input = build_python_project_explorer_input()

    # 2. Explorer reasons and produces a validated Tool Request.
    explorer_output = explorer.investigate(explorer_input)
    tool_request = explorer_output.to_tool_request()
    assert tool_request.tool == explorer_output.selected_tool

    # 3. Runtime (mocked) executes the Tool Request and returns an Observation.
    observation = runtime.execute(tool_request)
    assert observation["success"] is True
    assert len(runtime.call_log) == 1

    # 4. Runtime builds a Claim from the Observation (Runtime's job, simulated here).
    claim = ClaimInput(
        claim_id="claim-entrypoint",
        statement="Application entrypoint identified via read_file",
        node_id=explorer_output.node_id,
        evidence=[
            EvidenceInput(
                evidence_id="ev-from-observation",
                description=f"Observation from {tool_request.tool.value}: {observation['data']}",
                source=EvidenceSource.EXECUTION,
                supports_claim=True,
                node_id=explorer_output.node_id,
            )
        ],
    )

    # 5. Claim (+ context) is handed to Verification.
    verification_input = VerificationInput(
        investigation_id=explorer_input.investigation_id,
        claims=[claim],
        relevant_goals=explorer_input.active_goals,
    )
    assessment = verifier.verify(verification_input)

    # 6. Assessment should treat this as a supported, execution-backed claim.
    assert claim.claim_id in assessment.supported_claims
    assert assessment.investigation_id == explorer_input.investigation_id
    assert "Verification Report" in assessment.report_markdown


def test_nodejs_project_pipeline_runs_end_to_end():
    llm = MockLLMProvider()
    explorer = ExplorerAgent(llm)
    runtime = MockRuntimeExecutor()

    explorer_input = build_nodejs_project_explorer_input()
    output = explorer.investigate(explorer_input)
    observation = runtime.execute(output.to_tool_request())
    assert observation["success"] is True


def test_missing_dependency_project_explorer_avoids_repeating_failed_action():
    llm = MockLLMProvider()
    explorer = ExplorerAgent(llm)

    explorer_input = build_missing_dependency_explorer_input()
    output = explorer.investigate(explorer_input)
    # The plan must still be valid even though a previous action failed.
    assert output.node_id == "inspect_dependencies"
    assert len(output.execution_steps) >= 1


def test_contradictory_documentation_project_flags_contradiction():
    llm = MockLLMProvider()
    verifier = VerificationAgent(llm)

    verification_input = build_contradictory_documentation_verification_input()
    assessment = verifier.verify(verification_input)

    assert "claim-auth-required" in assessment.unresolved_claims
    contradiction_ids = {f.claim_id for f in assessment.contradictions}
    assert "claim-auth-required" in contradiction_ids


def test_failed_execution_project_produces_missing_evidence_and_recommendation():
    llm = MockLLMProvider()
    explorer = ExplorerAgent(llm)
    verifier = VerificationAgent(llm)

    explorer_input = build_failed_execution_explorer_input()
    explorer_output = explorer.investigate(explorer_input)
    assert explorer_output.node_id == "run_test_suite"

    verification_input = build_failed_execution_verification_input()
    assessment = verifier.verify(verification_input)
    assert "claim-tests-pass" in assessment.unresolved_claims
    assert any("claim-tests-pass" in m for m in assessment.missing_evidence)
