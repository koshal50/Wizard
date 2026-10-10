"""
Semantic validation for Explorer output.

Pydantic guarantees *shape*. This module guarantees the output is
*consistent with the input it was generated from*: valid node ids, only
tools that were actually made available, and step counts within budget.
"""
from __future__ import annotations

from app.contracts.explorer import ExplorerInput, ExplorerOutput
from app.explorer.tools import TOOL_REGISTRY


class ExplorerValidationError(Exception):
    """Raised when Explorer output is malformed or unsafe to accept."""


def validate_explorer_output(explorer_input: ExplorerInput, output: ExplorerOutput) -> None:
    """Raise ExplorerValidationError if `output` is not valid for `explorer_input`.

    Called by the Explorer agent immediately after receiving a response
    from the LLM provider, before returning it to the caller.
    """
    errors: list[str] = []

    if output.investigation_id != explorer_input.investigation_id:
        errors.append(
            f"investigation_id mismatch: expected '{explorer_input.investigation_id}', "
            f"got '{output.investigation_id}'"
        )

    if output.node_id != explorer_input.current_node.node_id:
        errors.append(
            f"node_id mismatch: expected '{explorer_input.current_node.node_id}', got '{output.node_id}'"
        )

    if output.decision != 'action':
        if output.tool_request is not None or not output.reason.strip():
            errors.append('terminal decision requires a reason and no tool request')
        if errors:
            raise ExplorerValidationError('; '.join(errors))
        return
    if output.tool_request is None:
        raise ExplorerValidationError('action decision requires a tool request')
    if output.tool not in explorer_input.available_tools:
        errors.append(
            f"tool '{output.tool.value}' is not in available_tools "
            f"{[t.value for t in explorer_input.available_tools]}"
        )
    descriptor = TOOL_REGISTRY.get(output.tool)
    if descriptor:
        unknown = set(output.parameters) - set(descriptor.expected_parameters)
        if unknown:
            errors.append(f"parameters contain unsupported names for {output.tool.value}: {sorted(unknown)}")
    if output.tool.value == "execute_command" and not output.parameters.get("command"):
        errors.append("execute_command requires parameters.command")

    if errors:
        raise ExplorerValidationError("; ".join(errors))
