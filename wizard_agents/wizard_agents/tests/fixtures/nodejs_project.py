"""Fixture data representing a typical Node.js project investigation."""
from __future__ import annotations

from app.contracts.common import RepositoryMetadata, ToolName
from app.contracts.explorer import ExplorerInput, InvestigationNode, Route


def build_nodejs_project_explorer_input() -> ExplorerInput:
    node = InvestigationNode(
        node_id="identify_application_entrypoint",
        goal="Determine which file is the Node.js application entrypoint",
    )
    route = Route(node_order=[node.node_id], current_index=0)
    return ExplorerInput(
        investigation_id="inv-fixture-nodejs",
        current_node=node,
        route=route,
        nodes=[node],
        repository_metadata=RepositoryMetadata(
            root_path="/repo",
            detected_languages=["javascript", "typescript"],
            detected_frameworks=["express"],
        ),
        available_tools=[ToolName.READ_FILE, ToolName.LIST_DIRECTORY, ToolName.SEARCH_FILES],
    )
