"""Chat endpoint. HTTP in, HTTP out -- no business logic.

Everything it reports (intent, route, sources) was decided by ``services/``;
this layer only translates and returns it.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import Container, current_user, get_container
from api.errors import MODEL_ERRORS, SESSION_ERRORS, error_responses
from models.auth import User
from models.conversation import TurnResult
from services.chat_service import ConversationForbidden, ConversationNotFound

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="Lo que escribio o dijo la persona.")
    conversation_id: UUID | None = Field(
        default=None,
        description="Omitir en el primer turno. En los siguientes, enviar el "
                    "conversation_id que devolvio el primer turno.",
    )


# Without explicit examples Swagger pre-fills conversation_id with a made-up
# UUID, and executing that as-is is a guaranteed 404. The first example, which
# Swagger shows by default, is the one that works as-is.
_EXAMPLES = {
    "nueva": {
        "summary": "Primer turno: conversacion nueva",
        "value": {"message": "a que hora puedo ir el fin de semana?"},
    },
    "continuar": {
        "summary": "Turno siguiente: misma conversacion",
        "description": "Reemplaza conversation_id por el que devolvio el primer turno.",
        "value": {
            "message": "y entre semana?",
            "conversation_id": "00000000-0000-0000-0000-000000000000",
        },
    },
}


@router.post(
    "/chat",
    response_model=TurnResult,
    responses=error_responses({
        **SESSION_ERRORS,
        403: "El conversation_id pertenece a otro usuario.",
        404: "No existe una conversacion con ese conversation_id. "
             "Para empezar una nueva, omitir el campo.",
        **MODEL_ERRORS,
    }),
)
async def chat(
    payload: ChatRequest = Body(openapi_examples=_EXAMPLES),
    user: User = Depends(current_user),
    container: Container = Depends(get_container),
) -> TurnResult:
    """Send one turn to the agent and get its reply.

    Requires the X-Session-Id header from POST /auth/login. Omit
    conversation_id to start a conversation; send back the one returned to
    continue it, so the agent remembers the previous turns.
    """
    try:
        return await container.chat.send(
            user=user,
            message=payload.message,
            conversation_id=payload.conversation_id,
        )
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConversationForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
