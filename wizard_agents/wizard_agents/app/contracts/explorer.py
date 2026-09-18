"""
Explorer Agent contracts.

Explorer REASONS about how a given investigation node should be
investigated and produces a validated Tool Request / Execution Plan.
Explorer never executes anything itself.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.contracts.common import (
    ExecutionBudget,
    ExecutionStep,
    PreviousAction,
    RepositoryMetadata,
    ToolName,
    ToolRequest,
)


class InvestigationNode(BaseModel):
    """A single node in the Investigation Planner's route.

    The Planner/Runtime component is responsible for constructing these;
    Explorer only consumes them.
    """

    node_id: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1, description="What this node is trying to establish")
    description: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list, description="node_ids that must complete first")
    planned_action: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "The action the Planner already attached to this node, as "
            "{'tool': str, 'params': {...}} — present when Runtime forwards a "
            "Planner-authored node. Explorer may honour it or override it, but "
            "should only override with a reason: the Planner usually knows which "
            "concrete tool this node needs."
        ),
    )


class Route(BaseModel):
    """Ordered traversal of nodes the Planner has decided on."""

    node_order: List[str] = Field(..., min_length=1, description="Ordered list of node_ids")
    current_index: int = Field(default=0, ge=0)

    @field_validator("current_index")
    @classmethod
    def _index_in_range(cls, v: int, info) -> int:
        node_order = info.data.get("node_order")
        if node_order is not None and v >= len(node_order):
            raise ValueError("current_index out of range for node_order")
        return v


class ExplorerInput(BaseModel):
    """Everything Explorer needs to reason about a single node.

    Field names intentionally mirror the leader-defined contract so the
    Investigation Planner / Runtime Engine can construct this directly.
    """

    investigation_id: str = Field(..., min_length=1)
    current_node: InvestigationNode
    route: Route
    nodes: List[InvestigationNode] = Field(
        default_factory=list, description="All nodes in the investigation, for cross-node context"
    )
    active_goals: List[str] = Field(default_factory=list)
    known_claims: List[str] = Field(
        default_factory=list, description="Short text summaries of claims already established"
    )
    context: Optional[str] = Field(default=None, description="Free-text additional context")
    missing_evidence: List[str] = Field(default_factory=list)
    previous_actions: List[PreviousAction] = Field(default_factory=list)
    available_tools: List[ToolName] = Field(
        default_factory=lambda: list(ToolName),
        description="Tools Runtime has made available for this investigation",
    )
    repository_metadata: Optional[RepositoryMetadata] = None
    execution_budget: ExecutionBudget = Field(default_factory=ExecutionBudget)

    @field_validator("current_node")
    @classmethod
    def _current_node_in_route(cls, v: InvestigationNode, info) -> InvestigationNode:
        route = info.data.get("route")
        if route is not None and v.node_id not in route.node_order:
            raise ValueError(
                f"current_node.node_id '{v.node_id}' is not present in route.node_order"
            )
        return v


class ExplorerOutput(BaseModel):
    """Explorer's validated Tool Request / Execution Plan for a node.

    This is the ONLY thing Explorer produces. It contains no observations,
    no claims, and no execution results -- those belong to Runtime.
    """

    investigation_id: str
    node_id: str
    purpose: str = Field(..., min_length=1, description="Why this investigation step matters")
    reasoning: str = Field(..., min_length=1, description="Explorer's reasoning trace")
    selected_tool: ToolName
    parameters: Dict[str, Any] = Field(default_factory=dict)
    command: Optional[str] = Field(default=None)
    execution_steps: List[ExecutionStep] = Field(..., min_length=1)
    expected_observation: str = Field(..., min_length=1)
    success_condition: str = Field(..., min_length=1)
    failure_condition: str = Field(..., min_length=1)
    next_node: Optional[str] = Field(
        default=None, description="node_id Runtime should move to next, or None if terminal"
    )
    fallback: Optional[str] = Field(
        default=None, description="What to do / escalate to if this plan fails"
    )

    def to_tool_request(self) -> ToolRequest:
        """Convenience conversion to the minimal ToolRequest Runtime consumes."""
        return ToolRequest(tool=self.selected_tool, command=self.command, parameters=self.parameters)

    @field_validator("command")
    @classmethod
    def _command_requires_execute_tool(cls, v: Optional[str], info) -> Optional[str]:
        tool = info.data.get("selected_tool")
        if v and tool != ToolName.EXECUTE_COMMAND:
            raise ValueError("command is only valid when selected_tool == execute_command")
        return v
