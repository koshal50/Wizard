"""
Verification Agent.

Verification critically reviews claims and evidence from the Claims
Graph and produces a structured markdown assessment. It never executes
commands, touches the repository, or modifies the Claims Graph / trust /
goal state -- see app/contracts/verification.py for the full contract.
"""
from __future__ import annotations

from app.contracts.verification import VerificationInput, VerificationOutput
from app.llm.base import LLMError, LLMProvider
from app.prompts.verification_prompts import VERIFICATION_SYSTEM_PROMPT, build_verification_user_prompt
from app.validation.verification_validation import (
    VerificationValidationError,
    validate_verification_output,
)


class VerificationAgentError(Exception):
    """Raised when Verification cannot produce a valid output for the given input."""


class VerificationAgent:
    """Verification Agent: claims graph info in, structured assessment out."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def verify(self, verification_input: VerificationInput) -> VerificationOutput:
        """Produce a validated VerificationOutput for `verification_input`.

        Raises VerificationAgentError if the LLM call fails or if the
        response cannot be validated as safe/consistent output.
        """
        user_prompt = build_verification_user_prompt(verification_input)

        try:
            output = self._llm.generate_structured(
                system_prompt=VERIFICATION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=VerificationOutput,
                metadata={"input": verification_input.model_dump(mode="json")},
            )
        except LLMError as exc:
            raise VerificationAgentError(f"Verification LLM call failed: {exc}") from exc

        try:
            validate_verification_output(verification_input, output)
        except VerificationValidationError as exc:
            raise VerificationAgentError(f"Verification output failed validation: {exc}") from exc

        return output
