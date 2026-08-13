from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_provider
from app.contracts.explorer import ExplorerInput, ExplorerOutput
from app.explorer.agent import ExplorerAgentError, ExplorerAgent
from app.llm.base import LLMProvider

router = APIRouter(prefix="/explorer", tags=["explorer"])


@router.post("/investigate", response_model=ExplorerOutput)
def investigate(payload: ExplorerInput, provider: LLMProvider = Depends(get_provider)) -> ExplorerOutput:
    agent = ExplorerAgent(provider)
    try:
        return agent.investigate(payload)
    except ExplorerAgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
