"""
Shared primitive types used across Explorer and Verification contracts.

These types are intentionally small and framework-agnostic so that other
Wizard components (Investigation Planner, Runtime Engine) can serialize /
deserialize them without importing agent-internal code.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ToolName(str, Enum):
    """Allow-listed tools that Explorer may request. Runtime owns execution.

    This is the single source of truth for "known tools". Explorer output
    validation rejects any tool not in this enum (see app/validation).

    Names must match the Runtime's own tool registry
    (wizard_kernel/control/tool_validator.py::_ALLOWED_TOOLS) verbatim — the
    Runtime validates what we request against that registry and rejects anything
    it does not recognise. An earlier revision called the directory listing
    "list_directory", which the Runtime has never accepted, so every listing
    proposal was silently rejected and fell back to the node plan.
    """

    READ_FILE = "read_file"
    SEARCH_FILES = "search_files"
    LIST_TREE = "list_tree"
    PATH_EXISTS = "path_exists"
    EXECUTE_COMMAND = "execute_command"

    # Long-running process control — the Runtime owns process handles.
    START_PROCESS = "start_process"
    READ_PROCESS = "read_process"
    KILL_PROCESS = "kill_process"
    LIST_PROCESSES = "list_processes"

    CHECK_PORT = "check_port"

    # Browser actions are ordinary tools to the Runtime (world/browser).
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_SNAPSHOT = "browser_snapshot"
    BROWSER_CLICK = "browser_click"
    BROWSER_TYPE = "browser_type"
    BROWSER_BACK = "browser_back"
    BROWSER_EXTRACT = "browser_extract"

    # Agent-side reasoning vocabulary with no Runtime tool behind them. They are
    # never in the `available_tools` the Runtime sends, so Explorer cannot
    # propose them; they remain here to describe intent in reasoning artifacts.
    INSPECT_CONFIGURATION = "inspect_configuration"
    TRACE_EXECUTION = "trace_execution"


class ExecutionStep(BaseModel):
    """A single ordered step Explorer proposes the Runtime carry out.

    Explorer produces these as *reasoning artifacts* only. Runtime decides
    whether/how to actually execute them.
    """

    step_number: int = Field(..., ge=1, description="1-indexed order of this step")
    description: str = Field(..., min_length=1, description="Human readable description of the step")
    tool: ToolName = Field(..., description="Tool this step relies on")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the tool call")

    @field_validator("description")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v


class ToolRequest(BaseModel):
    """The concrete tool invocation Explorer is requesting Runtime perform.

    This is a *request*, never an execution. Runtime validates it again
    against its own tool registry before doing anything.
    """

    tool: ToolName
    command: Optional[str] = Field(
        default=None,
        description="Shell/CLI command text, only meaningful when tool == execute_command",
    )
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def _command_requires_execute_tool(cls, v: Optional[str], info) -> Optional[str]:
        tool = info.data.get("tool")
        if v and tool != ToolName.EXECUTE_COMMAND:
            raise ValueError("command is only valid when tool == execute_command")
        if tool == ToolName.EXECUTE_COMMAND and not v:
            raise ValueError("execute_command requires a non-empty command")
        return v


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RepositoryMetadata(BaseModel):
    """Lightweight repository context supplied by Runtime/Planner to Explorer."""

    root_path: Optional[str] = None
    detected_languages: List[str] = Field(default_factory=list)
    detected_frameworks: List[str] = Field(default_factory=list)
    entrypoints: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class PreviousAction(BaseModel):
    """A record of a prior Explorer-requested action and its outcome.

    Supplied back into Explorer input so it can reason about what has
    already been tried (including failures) for a given node.
    """

    node_id: str
    tool: ToolName
    parameters: Dict[str, Any] = Field(default_factory=dict)
    outcome: Optional[str] = Field(
        default=None, description="Free-text summary of what happened, e.g. 'failed: file not found'"
    )
    succeeded: Optional[bool] = None


class ExecutionBudget(BaseModel):
    """Constraints Explorer must respect when proposing execution plans."""

    max_steps: int = Field(default=5, ge=1, le=50)
    max_tool_calls: int = Field(default=5, ge=1, le=50)
    time_budget_seconds: Optional[int] = Field(default=None, ge=1)
