"""
Explorer Agent.

Explorer reasons about HOW the Runtime should investigate a given node
and produces a validated Tool Request / Execution Plan. It never
executes tools, touches the repository, creates claims, or modifies
system state -- see the module docstring in app/contracts/explorer.py
for the full contract.
"""
from __future__ import annotations

from app.contracts.explorer import ExplorerInput, ExplorerOutput
from app.llm.base import LLMError, LLMProvider
from app.prompts.explorer_prompts import EXPLORER_SYSTEM_PROMPT, build_explorer_user_prompt
from app.validation.explorer_validation import ExplorerValidationError, validate_explorer_output


class ExplorerAgentError(Exception):
    """Raised when Explorer cannot produce a valid output for the given input."""


class ExplorerAgent:
    """Explorer Agent: nodes + route in, validated tool request/plan out."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def investigate(self, explorer_input: ExplorerInput) -> ExplorerOutput:
        """Produce a validated ExplorerOutput for `explorer_input`.

        Raises ExplorerAgentError if the LLM call fails or if the response
        cannot be validated as safe/consistent output.
        """
        user_prompt = build_explorer_user_prompt(explorer_input)

        try:
            output = self._llm.generate_structured(
                system_prompt=EXPLORER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=ExplorerOutput,
                metadata={"input": explorer_input.model_dump(mode="json")},
            )
        except LLMError as exc:
            raise ExplorerAgentError(f"Explorer LLM call failed: {exc}") from exc

        try:
            validate_explorer_output(explorer_input, output)
        except ExplorerValidationError as exc:
            raise ExplorerAgentError(f"Explorer output failed validation: {exc}") from exc

        return output
