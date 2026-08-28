"""Fixture data representing a typical Python project investigation."""
from __future__ import annotations

from app.contracts.common import RepositoryMetadata
from app.contracts.explorer import ExplorerInput, InvestigationNode, Route


def build_python_project_explorer_input() -> ExplorerInput:
    node = InvestigationNode(
        node_id="identify_application_entrypoint",
        goal="Determine which file is the application entrypoint",
    )
    route = Route(node_order=[node.node_id], current_index=0)
    return ExplorerInput(
        investigation_id="inv-fixture-python",
        current_node=node,
        route=route,
        nodes=[node],
        repository_metadata=RepositoryMetadata(
            root_path="/repo",
            detected_languages=["python"],
            detected_frameworks=["fastapi"],
        ),
    )
