from typing import Literal
from pydantic import BaseModel


class ToolRequest(BaseModel):
    tool: str
    parameters: dict
    reason: str = ""


class ExplorerResponse(BaseModel):
    investigation_id: str
    tool_request: ToolRequest


class VerifierAssessment(BaseModel):
    investigation_id: str
    assessment: Literal["overall_sufficient", "needs_more_work"]
    weak_claims: list[str] = []
    recommended_additional_investigations: list[str] = []
