from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_provider": os.environ.get("WIZARD_LLM_PROVIDER", "mock"),
    }
