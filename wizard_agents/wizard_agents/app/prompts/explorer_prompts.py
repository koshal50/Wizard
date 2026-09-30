"""Prompt templates for the Explorer Agent."""
from __future__ import annotations

import json

from app.contracts.explorer import ExplorerInput
from app.explorer.tools import describe_tools

EXPLORER_SYSTEM_PROMPT = """\
You are the Explorer Agent inside the Wizard investigation system.

Your ONLY job is to decide HOW the Runtime Engine should investigate a
single given node. You reason; you do not execute.

Rules you must follow:
- You may only select a tool from the `available_tools` list you are given.
- You may only produce a `command` field if `selected_tool` is `execute_command`.
- You must never claim to have executed anything, read a file, or observed
  a result -- you have not. You are only proposing a plan.
- You must ground `next_node` in the supplied `route`.
- Respect `execution_budget`: do not propose more steps than `max_steps`.
- If `previous_actions` shows a prior failed attempt at this node, propose
  a different tool or approach rather than repeating it verbatim.

Respond with a single JSON object matching the ExplorerOutput schema you
are given. Do not execute, invent evidence, or output anything besides
that JSON object.
"""


def build_explorer_user_prompt(explorer_input: ExplorerInput) -> str:
    tool_details = [
        {"name": tool.name.value, "description": tool.description, "expected_parameters": tool.expected_parameters}
        for tool in describe_tools(explorer_input.available_tools)
    ]
    return (
        "Investigation node to plan for:\n"
        f"{json.dumps(explorer_input.model_dump(mode='json'), indent=2)}\n\n"
        f"Available tool details:\n{json.dumps(tool_details, indent=2)}\n\n"
        "For the selected tool, include its expected parameters in `parameters`, using values from `current_node.planned_action` when available. Do not omit expected parameters.\n\n"
        "Produce an ExplorerOutput JSON object for this node."
    )
