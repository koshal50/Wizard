"""
Factory for selecting an LLMProvider based on environment configuration.

WIZARD_LLM_PROVIDER=mock (default) -> MockLLMProvider, no server needed (tests/offline).
WIZARD_LLM_PROVIDER=vllm            -> VLLMProvider, real runtime via a self-hosted
                                       open-source model on vLLM's OpenAI-compatible API.
"""
from __future__ import annotations

import os

from app.llm.base import LLMProvider
from app.llm.mock_provider import MockLLMProvider


def get_llm_provider() -> LLMProvider:
    provider_name = os.environ.get("WIZARD_LLM_PROVIDER", "mock").strip().lower()

    if provider_name == "mock":
        return MockLLMProvider()

    if provider_name == "vllm":
        from app.llm.vllm_provider import VLLMProvider  # local import: keeps import graph light

        return VLLMProvider()

    raise ValueError(
        f"Unknown WIZARD_LLM_PROVIDER='{provider_name}'. Supported: 'mock', 'vllm'."
    )
