from typing import Any
from pydantic import BaseModel


class ToolResult(BaseModel):
    ok: bool
    data: Any = None
    error: str | None = None
    meta: dict[str, Any] = {}


class CommandResult(BaseModel):
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
