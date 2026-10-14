"""
Explorer Agent contracts.

Explorer REASONS about how a given investigation node should be
investigated and produces a validated Tool Request / Execution Plan.
Explorer never executes anything itself.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.common import (
    ExecutionBudget,
    PreviousAction,
    RepositoryMetadata,
    ToolName,
    ToolRequest as KernelToolRequest,
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
    investigation: Dict[str, Any] = Field(default_factory=dict)
    goals: List[Dict[str, Any]] = Field(default_factory=list)
    plan: Dict[str, Any] = Field(default_factory=dict)
    node_selection: Dict[str, Any] = Field(default_factory=dict)
    successful_results: List[Dict[str, Any]] = Field(default_factory=list)
    recent_failures: List[Dict[str, Any]] = Field(default_factory=list)
    resources: Dict[str, Any] = Field(default_factory=dict)
    http: Dict[str, Any] = Field(default_factory=dict)
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


class ExplorerToolRequest(BaseModel):
    """One tool plus that tool's own arguments (never a cross-tool argument union)."""

    model_config = ConfigDict(extra="forbid")
    tool: ToolName
    # Scalars for most tools; browser_fill_form's `fields` is a list of
    # {selector, text} objects, so the value union also admits list/dict.
    parameters: Dict[str, "str | int | float | bool | None | list | dict"]


class ExplorerOutput(BaseModel):
    """One concise tactical decision; Runtime remains the execution authority."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    tool_request: ExplorerToolRequest | None = None
    decision: Literal['action', 'complete', 'incomplete'] = 'action'
    reason: str = ''

    @model_validator(mode='after')
    def decision_shape(self):
        if self.decision == 'action' and self.tool_request is None:
            raise ValueError('action decision requires tool_request')
        if self.decision != 'action' and (self.tool_request is not None or not self.reason.strip()):
            raise ValueError('terminal decision requires a reason and no tool_request')
        return self

    @property
    def tool(self) -> ToolName:
        return self.tool_request.tool

    @property
    def parameters(self) -> Dict[str, str | int | float | bool | None]:
        return self.tool_request.parameters

    def to_tool_request(self) -> KernelToolRequest:
        """Convenience conversion to the minimal ToolRequest Runtime consumes."""
        params = dict(self.parameters)
        command = params.pop("command", None) if self.tool == ToolName.EXECUTE_COMMAND else None
        return KernelToolRequest(tool=self.tool, command=command, parameters=params)
