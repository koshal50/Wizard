from typing import Any
from datetime import datetime
from pydantic import BaseModel


class Claim(BaseModel):
    id: str
    investigation_id: str
    claim_type: str
    key: str
    value: Any
    created_at: datetime
