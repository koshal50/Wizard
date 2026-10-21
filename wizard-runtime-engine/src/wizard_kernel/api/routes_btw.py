"""Stateless conversation transport. Only usage metadata enters persistence."""

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from wizard_kernel.api.account_auth import authenticated_account_id
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.ports.model import ModelFailure, ModelPolicy
from wizard_kernel.storage.usage import operation

router = APIRouter(prefix="/v1/btw", tags=["conversation"])


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=60000)


class ConversationRequest(BaseModel):
    conversation_id: UUID
    session_id: UUID
    messages: list[Message] = Field(min_length=1, max_length=500)


class Reply(BaseModel):
    text: str = Field(min_length=1)


@router.post("")
def reply(req: ConversationRequest, account_id: Annotated[str | None, Depends(authenticated_account_id)]):
    if req.messages[-1].role != "user" or not req.messages[-1].content.strip():
        raise HTTPException(422, "A nonempty user question is required")
    # Each turn has its own metadata-only usage run; neither parent nor transcript
    # is registered with InvestigationManager or written through fs_store.
    turn = SimpleNamespace(id="btw-" + req.conversation_id.hex + "-" + uuid4().hex, intent="btw",
                           account_id=account_id if isinstance(account_id, str) else None,
                           usage_session_id="btw-session:" + str(req.session_id),
                           started_at=datetime.now(UTC), updated_at=datetime.now(UTC),
                           state=LifecycleState.completed)
    try:
        with operation(turn):
            try:
                result = ModelPolicy().request("btw", {"messages": [m.model_dump() for m in req.messages]},
                                               Reply, deadline=time.monotonic() + 60)
                if not result.text.strip():
                    raise ModelFailure("empty", "Provider returned an empty answer")
            except Exception:
                turn.state = LifecycleState.failed
                raise
            finally:
                turn.updated_at = datetime.now(UTC)
        return {"conversation_id": str(req.conversation_id), "text": result.text}
    except ModelFailure as exc:
        # No provider response body or private prompt is exposed to the UI.
        raise HTTPException(502, "Side conversation could not respond (" + exc.kind + "). Try again.") from None
