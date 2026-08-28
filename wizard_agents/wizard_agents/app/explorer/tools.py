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
    ToolName.LIST_DIRECTORY: ToolDescriptor(
        ToolName.LIST_DIRECTORY,
        "List the contents of a directory in the repository.",
        ["path"],
    ),
    ToolName.EXECUTE_COMMAND: ToolDescriptor(
        ToolName.EXECUTE_COMMAND,
        "Execute a shell/CLI command inside the sandboxed repository environment.",
        ["command", "working_directory"],
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
