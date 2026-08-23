from pydantic import BaseModel


class ReportResponse(BaseModel):
    investigation_id: str
    report_markdown: str
    report_path: str
