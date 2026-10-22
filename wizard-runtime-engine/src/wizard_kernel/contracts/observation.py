from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from wizard_kernel.contracts.evidence import EvidenceCategory

ObsType = Literal[
    "filesystem", "file_content", "command_result",
    "search_hits", "port_check", "path_check",
    "page_content", "browser_action", "http_response", "agent_failure", "artifact",
]


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    investigation_id: str
    node_id: str
    source_tool: str
    obs_type: ObsType
    payload: dict[str, Any]
    created_at: datetime
    goal_id: str | None = None
    tool_request_id: str | None = None
    execution_id: str | None = None
    evidence_categories: list[EvidenceCategory] = []
    success: bool = False
