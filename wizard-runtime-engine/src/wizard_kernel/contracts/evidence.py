from typing import Literal
from datetime import datetime
from pydantic import BaseModel

SourceTier = Literal["execution", "config_parse", "documentation"]
SupportType = Literal["support", "contradict"]
EvidenceCategory = Literal[
    "repository_read", "command_execution", "process_execution", "http_response",
    "browser_navigation", "browser_observation", "browser_interaction", "browser_form_input", "docker_execution",
]


class Evidence(BaseModel):
    id: str
    claim_id: str
    observation_ids: list[str]
    support_type: SupportType
    source_tier: SourceTier
    created_at: datetime
