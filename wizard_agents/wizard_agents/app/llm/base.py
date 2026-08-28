"""
LLM provider abstraction.

Agents must never depend on a specific LLM vendor. They depend only on
this interface, so a provider can be swapped via configuration/env vars
without touching agent logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised when a provider fails to produce a usable response."""


class LLMProvider(ABC):
    """Abstract interface every LLM provider must implement."""

    @abstractmethod
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        *,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> T:
        """Generate a response and parse/validate it into `response_model`.

        Implementations MUST raise LLMError (not return partial/invalid
        data) if the underlying call fails or returns unparsable content.
        Callers are still responsible for their own semantic validation
        beyond basic pydantic parsing (see app/validation).
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for logging/debugging, e.g. 'mock' or 'vllm'."""
        raise NotImplementedError
