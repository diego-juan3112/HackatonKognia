"""Chat endpoint. HTTP in, HTTP out -- no business logic.

Everything it reports (intent, route, sources) was decided by ``services/``;
this layer only translates and returns it.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import Container, current_user, get_container
from models.auth import User
from models.conversation import TurnResult
from services.chat_service import ConversationForbidden, ConversationNotFound

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: UUID | None = Field(
        default=None,
        description="Omitir para empezar una conversacion nueva.",
    )


@router.post("/chat", response_model=TurnResult)
async def chat(
    payload: ChatRequest,
    user: User = Depends(current_user),
    container: Container = Depends(get_container),
) -> TurnResult:
    try:
        return await container.chat.send(
            user_id=user.id,
            message=payload.message,
            conversation_id=payload.conversation_id,
        )
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConversationForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
