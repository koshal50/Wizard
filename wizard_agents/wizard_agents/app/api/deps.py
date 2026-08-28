"""Shared FastAPI dependencies. Kept separate so tests can override them
via app.dependency_overrides without touching route modules."""
from __future__ import annotations

from functools import lru_cache

from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider


@lru_cache(maxsize=1)
def _cached_provider() -> LLMProvider:
    return get_llm_provider()


def get_provider() -> LLMProvider:
    return _cached_provider()
