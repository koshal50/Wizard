"""
Tool registry.

Explorer may only *request* tools that Runtime has declared available.
This module owns the canonical description of each tool (for prompting
and documentation) and a small allow-list check helper. It does NOT
execute anything -- actual execution is entirely Runtime's responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from app.contracts.common import ToolName


@dataclass(frozen=True)
class ToolDescriptor:
    name: ToolName
    description: str
    expected_parameters: List[str]


TOOL_REGISTRY: Dict[ToolName, ToolDescriptor] = {
    ToolName.READ_FILE: ToolDescriptor(
        ToolName.READ_FILE,
        "Read the contents of a single file from the repository.",
        ["path"],
    ),
    ToolName.SEARCH_FILES: ToolDescriptor(
        ToolName.SEARCH_FILES,
        "Search repository files for a text pattern or query.",
        ["query", "path_glob"],
    ),
    ToolName.LIST_TREE: ToolDescriptor(
        ToolName.LIST_TREE,
        "List the contents of a directory in the repository.",
        ["path"],
    ),
    ToolName.PATH_EXISTS: ToolDescriptor(
        ToolName.PATH_EXISTS,
        "Check whether a path exists in the repository.",
        ["path"],
    ),
    ToolName.EXECUTE_COMMAND: ToolDescriptor(
        ToolName.EXECUTE_COMMAND,
        "Execute a shell/CLI command inside the sandboxed repository environment.",
        ["command", "working_directory"],
    ),
    ToolName.CHECK_PORT: ToolDescriptor(
        ToolName.CHECK_PORT,
        "Check whether a TCP port is listening (runtime liveness probe).",
        ["port"],
    ),
    ToolName.START_PROCESS: ToolDescriptor(
        ToolName.START_PROCESS,
        "Start a long-running process and return a handle the Runtime owns.",
        ["command"],
    ),
    ToolName.READ_PROCESS: ToolDescriptor(
        ToolName.READ_PROCESS,
        "Read buffered output from a previously started process.",
        ["handle_id"],
    ),
    ToolName.KILL_PROCESS: ToolDescriptor(
        ToolName.KILL_PROCESS,
        "Terminate a previously started process.",
        ["handle_id"],
    ),
    ToolName.LIST_PROCESSES: ToolDescriptor(
        ToolName.LIST_PROCESSES,
        "List the processes this investigation currently owns.",
        [],
    ),
    ToolName.BROWSER_NAVIGATE: ToolDescriptor(
        ToolName.BROWSER_NAVIGATE,
        "Navigate the investigation's browser to a URL.",
        ["url"],
    ),
    ToolName.BROWSER_SNAPSHOT: ToolDescriptor(
        ToolName.BROWSER_SNAPSHOT,
        "Capture the current page's accessibility snapshot.",
        [],
    ),
    ToolName.BROWSER_CLICK: ToolDescriptor(
        ToolName.BROWSER_CLICK,
        "Click an element in the live page.",
        ["selector"],
    ),
    ToolName.BROWSER_TYPE: ToolDescriptor(
        ToolName.BROWSER_TYPE,
        "Type text into an element in the live page.",
        ["selector", "text"],
    ),
    ToolName.BROWSER_BACK: ToolDescriptor(
        ToolName.BROWSER_BACK,
        "Navigate the browser back one history entry.",
        [],
    ),
    ToolName.BROWSER_EXTRACT: ToolDescriptor(
        ToolName.BROWSER_EXTRACT,
        "Extract structured content from the current page.",
        ["selector"],
    ),
    ToolName.INSPECT_CONFIGURATION: ToolDescriptor(
        ToolName.INSPECT_CONFIGURATION,
        "Inspect a configuration file/source (env, settings, manifest) for specific keys.",
        ["target"],
    ),
    ToolName.TRACE_EXECUTION: ToolDescriptor(
        ToolName.TRACE_EXECUTION,
        "Trace how a given entrypoint is reached / executed through the codebase.",
        ["entrypoint"],
    ),
}


def default_available_tools() -> List[ToolName]:
    """All tools known to the registry. Runtime may supply a narrower set."""
    return list(TOOL_REGISTRY.keys())


def is_tool_allowed(tool: ToolName, available_tools: Iterable[ToolName]) -> bool:
    return tool in set(available_tools)


def describe_tools(available_tools: Iterable[ToolName]) -> List[ToolDescriptor]:
    return [TOOL_REGISTRY[t] for t in available_tools if t in TOOL_REGISTRY]
