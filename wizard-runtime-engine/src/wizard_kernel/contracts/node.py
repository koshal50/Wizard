from typing import Any, Literal
from enum import Enum
from pydantic import BaseModel


class HypothesisKind(str, Enum):
    exit_code_in = "exit_code_in"
    stdout_contains = "stdout_contains"
    file_exists = "file_exists"
    json_path_equals = "json_path_equals"
    http_status = "http_status"
    always_success = "always_success"
    manual_escalate = "manual_escalate"


class Hypothesis(BaseModel):
    kind: HypothesisKind
    success_values: list[Any] = []
    failure_values: list[Any] = []
    pattern: str | None = None
    json_path: str | None = None


class ClaimTemplate(BaseModel):
    claim_type: str
    key: str
    value: Any


NodeType = Literal["discovery", "read", "execute", "parse", "verify", "planner", "checkpoint"]
NodeState = Literal["waiting", "running", "complete", "failed", "blocked"]


class InvestigationNode(BaseModel):
    id: str
    type: NodeType
    action: dict[str, Any]
    hypothesis: Hypothesis
    on_success: ClaimTemplate | None = None
    on_failure: ClaimTemplate | None = None
    escalate_when: str = "exit_code_not_in_success_or_failure"
    depends_on: list[str] = []
    parent_id: str | None = None
    goal_id: str | None = None
    state: NodeState = "waiting"
    observation_ids: list[str] = []
    claim_ids: list[str] = []
