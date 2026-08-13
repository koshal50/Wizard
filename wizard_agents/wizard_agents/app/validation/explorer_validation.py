"""
Semantic validation for Explorer output.

Pydantic guarantees *shape*. This module guarantees the output is
*consistent with the input it was generated from*: valid node ids, only
tools that were actually made available, and step counts within budget.
"""
from __future__ import annotations

from app.contracts.explorer import ExplorerInput, ExplorerOutput


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

    all_node_ids = {n.node_id for n in explorer_input.nodes} | set(explorer_input.route.node_order)
    if output.next_node is not None and output.next_node not in all_node_ids:
        errors.append(f"next_node '{output.next_node}' is not a known node id")

    if output.selected_tool not in explorer_input.available_tools:
        errors.append(
            f"selected_tool '{output.selected_tool.value}' is not in available_tools "
            f"{[t.value for t in explorer_input.available_tools]}"
        )

    for step in output.execution_steps:
        if step.tool not in explorer_input.available_tools:
            errors.append(
                f"execution_steps references unavailable tool '{step.tool.value}' "
                f"(step {step.step_number})"
            )

    if len(output.execution_steps) > explorer_input.execution_budget.max_steps:
        errors.append(
            f"execution_steps has {len(output.execution_steps)} steps, exceeding "
            f"execution_budget.max_steps={explorer_input.execution_budget.max_steps}"
        )

    step_numbers = [s.step_number for s in output.execution_steps]
    if step_numbers != sorted(step_numbers):
        errors.append("execution_steps must be ordered by ascending step_number")
    if len(set(step_numbers)) != len(step_numbers):
        errors.append("execution_steps contains duplicate step_number values")

    if output.command is not None and output.selected_tool.value != "execute_command":
        errors.append("command was supplied but selected_tool is not 'execute_command'")

    if errors:
        raise ExplorerValidationError("; ".join(errors))
