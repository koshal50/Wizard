from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_provider
from app.contracts.verification import VerificationInput, VerificationOutput
from app.llm.base import LLMProvider
from app.verification.agent import VerificationAgent, VerificationAgentError

router = APIRouter(prefix="/verification", tags=["verification"])


@router.post("/verify", response_model=VerificationOutput)
def verify(
    payload: VerificationInput, provider: LLMProvider = Depends(get_provider)
) -> VerificationOutput:
    agent = VerificationAgent(provider)
    try:
        return agent.verify(payload)
    except VerificationAgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
