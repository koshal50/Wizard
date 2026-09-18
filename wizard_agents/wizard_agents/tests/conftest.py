from __future__ import annotations

import pytest

from app.contracts.common import ExecutionBudget, PreviousAction, RepositoryMetadata, ToolName
from app.contracts.explorer import ExplorerInput, InvestigationNode, Route
from app.contracts.verification import ClaimInput, EvidenceInput, VerificationInput
from app.llm.mock_provider import MockLLMProvider


@pytest.fixture()
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


# -- Explorer fixtures ---------------------------------------------------


@pytest.fixture()
def python_project_node() -> InvestigationNode:
    return InvestigationNode(
        node_id="identify_application_entrypoint",
        goal="Determine which file is the application entrypoint",
        description="Locate the main module the Python app is launched from",
    )


@pytest.fixture()
def python_project_route(python_project_node: InvestigationNode) -> Route:
    return Route(node_order=[python_project_node.node_id, "inspect_dependencies"], current_index=0)


@pytest.fixture()
def python_project_explorer_input(
    python_project_node: InvestigationNode, python_project_route: Route
) -> ExplorerInput:
    return ExplorerInput(
        investigation_id="inv-python-1",
        current_node=python_project_node,
        route=python_project_route,
        nodes=[
            python_project_node,
            InvestigationNode(node_id="inspect_dependencies", goal="List declared dependencies"),
        ],
        active_goals=["Understand app startup"],
        known_claims=[],
        missing_evidence=["entrypoint file"],
        previous_actions=[],
        available_tools=list(ToolName),
        repository_metadata=RepositoryMetadata(
            root_path="/repo",
            detected_languages=["python"],
            detected_frameworks=["fastapi"],
            entrypoints=[],
        ),
        execution_budget=ExecutionBudget(max_steps=3, max_tool_calls=3),
    )


@pytest.fixture()
def nodejs_project_explorer_input() -> ExplorerInput:
    node = InvestigationNode(node_id="identify_application_entrypoint", goal="Find the Node.js entrypoint")
    route = Route(node_order=[node.node_id], current_index=0)
    return ExplorerInput(
        investigation_id="inv-node-1",
        current_node=node,
        route=route,
        nodes=[node],
        repository_metadata=RepositoryMetadata(
            root_path="/repo", detected_languages=["javascript"], detected_frameworks=["express"]
        ),
        available_tools=[ToolName.READ_FILE, ToolName.LIST_TREE],
    )


@pytest.fixture()
def failed_previous_action_explorer_input(python_project_explorer_input: ExplorerInput) -> ExplorerInput:
    data = python_project_explorer_input.model_dump()
    data["previous_actions"] = [
        PreviousAction(
            node_id="identify_application_entrypoint",
            tool=ToolName.SEARCH_FILES,
            parameters={"query": "main"},
            outcome="failed: no matches found",
            succeeded=False,
        ).model_dump()
    ]
    return ExplorerInput.model_validate(data)


# -- Verification fixtures -----------------------------------------------


@pytest.fixture()
def supported_claim() -> ClaimInput:
    return ClaimInput(
        claim_id="claim-supported",
        statement="The application entrypoint is app/main.py",
        evidence=[
            EvidenceInput(
                evidence_id="ev-1",
                description="Running `python app/main.py` starts the server",
                source="execution",
                supports_claim=True,
            )
        ],
    )


@pytest.fixture()
def weak_claim() -> ClaimInput:
    return ClaimInput(
        claim_id="claim-weak",
        statement="The application uses PostgreSQL",
        evidence=[
            EvidenceInput(
                evidence_id="ev-2",
                description="README.md mentions PostgreSQL support",
                source="documentation",
                supports_claim=True,
            )
        ],
    )


@pytest.fixture()
def contradicted_claim() -> ClaimInput:
    return ClaimInput(
        claim_id="claim-contradicted",
        statement="Authentication is required for all endpoints",
        evidence=[
            EvidenceInput(
                evidence_id="ev-3",
                description="auth middleware is registered globally",
                source="static_analysis",
                supports_claim=True,
            ),
            EvidenceInput(
                evidence_id="ev-4",
                description="/health endpoint responds without credentials",
                source="execution",
                supports_claim=False,
            ),
        ],
    )


@pytest.fixture()
def missing_evidence_claim() -> ClaimInput:
    return ClaimInput(claim_id="claim-missing", statement="Rate limiting is enabled", evidence=[])


@pytest.fixture()
def verification_input_multi(
    supported_claim: ClaimInput,
    weak_claim: ClaimInput,
    contradicted_claim: ClaimInput,
    missing_evidence_claim: ClaimInput,
) -> VerificationInput:
    return VerificationInput(
        investigation_id="inv-verify-1",
        claims=[supported_claim, weak_claim, contradicted_claim, missing_evidence_claim],
        relevant_goals=["Assess security posture"],
    )
