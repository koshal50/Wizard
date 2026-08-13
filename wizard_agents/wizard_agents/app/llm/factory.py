"""
Factory for selecting an LLMProvider based on environment configuration.

WIZARD_LLM_PROVIDER=mock (default) -> MockLLMProvider, no API key needed.
WIZARD_LLM_PROVIDER=anthropic      -> AnthropicProvider, requires ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import os

from app.llm.base import LLMProvider
from app.llm.mock_provider import MockLLMProvider


def get_llm_provider() -> LLMProvider:
    provider_name = os.environ.get("WIZARD_LLM_PROVIDER", "mock").strip().lower()

    if provider_name == "mock":
        return MockLLMProvider()

    if provider_name == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider  # local import: optional dep

        return AnthropicProvider()

    raise ValueError(
        f"Unknown WIZARD_LLM_PROVIDER='{provider_name}'. Supported: 'mock', 'anthropic'."
    )
