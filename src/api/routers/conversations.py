"""Conversation listing and readable history.

Reads from our ``messages`` table, not from the LangGraph checkpointer: the
checkpointer holds serialised graph state that is not meant to be displayed.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import Container, current_user, get_container
from models.auth import Conversation, MessageRecord, User
from services.chat_service import ConversationForbidden, ConversationNotFound

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[Conversation])
async def list_conversations(
    user: User = Depends(current_user),
    container: Container = Depends(get_container),
) -> list[Conversation]:
    return await container.chat.list_conversations(user.id)


@router.post("", response_model=Conversation, status_code=201)
async def create_conversation(
    user: User = Depends(current_user),
    container: Container = Depends(get_container),
) -> Conversation:
    return await container.conversations.create(
        user_id=user.id, domain=container.domain.name
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageRecord])
async def conversation_history(
    conversation_id: UUID,
    user: User = Depends(current_user),
    container: Container = Depends(get_container),
) -> list[MessageRecord]:
    try:
        return await container.chat.history(user.id, conversation_id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConversationForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
