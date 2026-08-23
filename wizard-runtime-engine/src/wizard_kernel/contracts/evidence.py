from typing import Literal
from datetime import datetime
from pydantic import BaseModel

SourceTier = Literal["execution", "config_parse", "documentation"]
SupportType = Literal["support", "contradict"]


class Evidence(BaseModel):
    id: str
    claim_id: str
    observation_ids: list[str]
    support_type: SupportType
    source_tier: SourceTier
    created_at: datetime
