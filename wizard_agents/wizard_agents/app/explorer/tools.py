"""Tool descriptions shared by Explorer prompting and its strict output schema."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from app.contracts.common import ToolName


@dataclass(frozen=True)
class ToolDescriptor:
    name: ToolName
    description: str
    expected_parameters: Dict[str, str]


TOOL_REGISTRY: Dict[ToolName, ToolDescriptor] = {
    ToolName.READ_FILE: ToolDescriptor(ToolName.READ_FILE, "Read a repository file.", {"path": "string", "max_bytes": "integer"}),
    ToolName.SEARCH_FILES: ToolDescriptor(ToolName.SEARCH_FILES, "Search repository files.", {"pattern": "string", "glob": "string"}),
    ToolName.LIST_TREE: ToolDescriptor(ToolName.LIST_TREE, "List repository files.", {"max_depth": "integer"}),
    ToolName.PATH_EXISTS: ToolDescriptor(ToolName.PATH_EXISTS, "Check a repository path.", {"path": "string"}),
    ToolName.EXECUTE_COMMAND: ToolDescriptor(ToolName.EXECUTE_COMMAND, "Execute a command in the sandbox.", {"command": "string", "cwd": "string", "timeout_sec": "integer"}),
    ToolName.CHECK_PORT: ToolDescriptor(ToolName.CHECK_PORT, "Check whether a TCP port is listening.", {"port": "integer", "host": "string"}),
    ToolName.HTTP_REQUEST: ToolDescriptor(ToolName.HTTP_REQUEST, "Make an allow-listed HTTP request.", {"url": "string", "method": "string", "body": "string"}),
    ToolName.START_PROCESS: ToolDescriptor(ToolName.START_PROCESS, "Start a long-running process owned by Runtime.", {"command": "string", "cwd": "string"}),
    ToolName.READ_PROCESS: ToolDescriptor(ToolName.READ_PROCESS, "Read output from a Runtime-owned process.", {"handle_id": "string"}),
    ToolName.KILL_PROCESS: ToolDescriptor(ToolName.KILL_PROCESS, "Stop a Runtime-owned process.", {"handle_id": "string"}),
    ToolName.LIST_PROCESSES: ToolDescriptor(ToolName.LIST_PROCESSES, "List Runtime-owned processes.", {}),
    ToolName.BROWSER_NAVIGATE: ToolDescriptor(ToolName.BROWSER_NAVIGATE, "Navigate the investigation browser.", {"url": "string"}),
    ToolName.BROWSER_SNAPSHOT: ToolDescriptor(ToolName.BROWSER_SNAPSHOT, "Capture the current page accessibility snapshot.", {}),
    ToolName.BROWSER_CLICK: ToolDescriptor(ToolName.BROWSER_CLICK, "Click a visible page control using its exact observed controls[].selector value.", {"selector": "string"}),
    ToolName.BROWSER_TYPE: ToolDescriptor(ToolName.BROWSER_TYPE, "Fill a visible textbox using its exact observed controls[].selector value and a supplied non-secret test value.", {"selector": "string", "text": "string"}),
    ToolName.BROWSER_FILL_FORM: ToolDescriptor(ToolName.BROWSER_FILL_FORM, "Fill several visible form fields in one action. Pass fields as a list of {selector, text} using exact observed controls[].selector values; does NOT submit the form.", {"fields": "array"}),
    ToolName.BROWSER_BACK: ToolDescriptor(ToolName.BROWSER_BACK, "Navigate back in the investigation browser.", {}),
    ToolName.BROWSER_EXTRACT: ToolDescriptor(ToolName.BROWSER_EXTRACT, "Extract structured content from the current page.", {}),
    ToolName.INSPECT_CONFIGURATION: ToolDescriptor(ToolName.INSPECT_CONFIGURATION, "Inspect a configuration source.", {"target": "string"}),
    ToolName.TRACE_EXECUTION: ToolDescriptor(ToolName.TRACE_EXECUTION, "Trace an execution entrypoint.", {"entrypoint": "string"}),
}


def default_available_tools() -> List[ToolName]:
    return list(TOOL_REGISTRY)


def is_tool_allowed(tool: ToolName, available_tools: Iterable[ToolName]) -> bool:
    return tool in set(available_tools)


def describe_tools(available_tools: Iterable[ToolName]) -> List[ToolDescriptor]:
    return [TOOL_REGISTRY[t] for t in available_tools if t in TOOL_REGISTRY]
