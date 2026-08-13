"""
MockRuntimeExecutor: a fake Runtime used ONLY by this subsystem's own
tests/examples to exercise the full Explorer -> execution -> Verification
flow without a real Runtime Engine. This is NOT the real Runtime Engine
and must never be imported by production agent code paths -- it exists
purely so the Agent System can be demonstrated/tested standalone.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.adapters.runtime_adapter import Observation, RuntimeExecutor
from app.contracts.common import ToolName, ToolRequest


class MockRuntimeExecutor(RuntimeExecutor):
    """Returns canned observations keyed by tool, optionally overridden
    per-call via `fixture_responses`. Never touches a real filesystem."""

    def __init__(self, fixture_responses: Dict[str, Any] | None = None) -> None:
        self._fixture_responses = fixture_responses or {}
        self.call_log: List[ToolRequest] = []

    def execute(self, tool_request: ToolRequest) -> Observation:
        self.call_log.append(tool_request)

        key = tool_request.tool.value
        if key in self._fixture_responses:
            payload = self._fixture_responses[key]
            return Observation(tool=key, success=True, data=payload)

        canned = {
            ToolName.READ_FILE: {"content": "# mock file contents"},
            ToolName.SEARCH_FILES: {"matches": []},
            ToolName.LIST_DIRECTORY: {"entries": []},
            ToolName.EXECUTE_COMMAND: {"stdout": "", "stderr": "", "exit_code": 0},
            ToolName.INSPECT_CONFIGURATION: {"config": {}},
            ToolName.TRACE_EXECUTION: {"trace": []},
        }
        return Observation(tool=key, success=True, data=canned.get(tool_request.tool, {}))
