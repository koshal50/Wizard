from typing import Literal
from pydantic import BaseModel


class ToolRequest(BaseModel):
    tool: str
    parameters: dict
    reason: str = ""


class ExplorerResponse(BaseModel):
    investigation_id: str
    node_id: str | None = None
    tool_request: ToolRequest | None = None
    decision: Literal['action', 'complete', 'incomplete'] = 'action'
    reason: str = ''


class VerifierAssessment(BaseModel):
    investigation_id: str
    assessment: Literal["overall_sufficient", "needs_more_work"]
    weak_claims: list[str] = []
    recommended_additional_investigations: list[str] = []
    report_markdown: str = ''
