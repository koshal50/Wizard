from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict

ObsType = Literal[
    "filesystem", "file_content", "command_result",
    "search_hits", "port_check", "path_check",
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
