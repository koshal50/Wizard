"""Fixture data representing an investigation where a previous attempt to
inspect dependencies failed because a dependency file could not be found."""
from __future__ import annotations

from app.contracts.common import PreviousAction, RepositoryMetadata, ToolName
from app.contracts.explorer import ExplorerInput, InvestigationNode, Route


def build_missing_dependency_explorer_input() -> ExplorerInput:
    node = InvestigationNode(
        node_id="inspect_dependencies",
        goal="Determine which package manager and dependencies the project uses",
    )
    route = Route(node_order=[node.node_id], current_index=0)
    return ExplorerInput(
        investigation_id="inv-fixture-missing-dep",
        current_node=node,
        route=route,
        nodes=[node],
        missing_evidence=["dependency manifest"],
        previous_actions=[
            PreviousAction(
                node_id="inspect_dependencies",
                tool=ToolName.READ_FILE,
                parameters={"path": "requirements.txt"},
                outcome="failed: file not found",
                succeeded=False,
            )
        ],
        repository_metadata=RepositoryMetadata(root_path="/repo", detected_languages=["python"]),
    )
