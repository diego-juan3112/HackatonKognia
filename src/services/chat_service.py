"""One turn of conversation, end to end.

Lives in ``services/`` rather than in the router because deciding what a turn
means -- which conversation it belongs to, what gets persisted, what the client
is told -- is business logic, and rule R-01 keeps ``api/`` free of it.

The router's job shrinks to: validate the HTTP shape, call this, return.
"""

from __future__ import annotations

from uuid import UUID

from models.auth import Conversation, MessageRecord, User
from models.conversation import RouteDecision, TurnResult
from models.domain_config import DomainSpec
from models.ports import ConversationRepositoryPort
from services.graph.state import UserContext, initial_state


class ConversationNotFound(LookupError):
    """The conversation does not exist."""


class ConversationForbidden(PermissionError):
    """The conversation exists but belongs to somebody else."""


def _context_for(user: User) -> UserContext:
    """What the graph is told about the person. Only what it needs."""
    return UserContext(
        user_id=str(user.id),
        display_name=user.display_name,
        cedula_last4=user.cedula[-4:],
    )


class ChatService:
    """Orchestrates: resolve conversation -> run the graph -> persist the turn."""

    def __init__(
        self,
        graph,
        conversations: ConversationRepositoryPort,
        domain: DomainSpec,
    ) -> None:
        self._graph = graph
        self._conversations = conversations
        self._domain = domain

    async def _resolve(self, user_id: UUID, conversation_id: UUID | None) -> Conversation:
        """Get the requested conversation, or start a new one."""
        if conversation_id is None:
            return await self._conversations.create(user_id=user_id, domain=self._domain.name)

        conversation = await self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFound(f"No existe la conversacion {conversation_id}.")
        # Without this check any authenticated user could read and write into
        # anyone else's thread just by guessing a UUID.
        if conversation.user_id != user_id:
            raise ConversationForbidden("Esa conversacion pertenece a otro usuario.")
        return conversation

    async def send(
        self,
        user: User,
        message: str,
        conversation_id: UUID | None = None,
    ) -> TurnResult:
        conversation = await self._resolve(user.id, conversation_id)

        await self._conversations.append_message(
            conversation_id=conversation.id, role="user", content=message
        )

        # thread_id is what the checkpointer resumes the graph state by; it is
        # what makes this turn aware of the previous ones.
        result = await self._graph.ainvoke(
            initial_state(message, user=_context_for(user)),
            config={"configurable": {"thread_id": conversation.thread_id}},
        )

        # .text, not str(.content): in langchain-core 1.x a model reply can be a
        # list of content blocks, and str() of that list is not the answer.
        reply = result["messages"][-1].text if result.get("messages") else ""
        route = result.get("route") or RouteDecision.ANSWER
        sources = sorted({item.source for item in result.get("retrieved", [])})

        await self._conversations.append_message(
            conversation_id=conversation.id,
            role="agent",
            content=reply,
            intent=result.get("intent"),
            route=str(route),
            sources=sources,
        )

        return TurnResult(
            reply=reply,
            thread_id=conversation.thread_id,
            conversation_id=conversation.id,
            intent=result.get("intent"),
            route=route,
            missing_fields=result.get("missing_fields", []),
            sources=sources,
        )

    async def list_conversations(self, user_id: UUID) -> list[Conversation]:
        return await self._conversations.list_for_user(user_id)

    async def history(self, user_id: UUID, conversation_id: UUID) -> list[MessageRecord]:
        await self._resolve(user_id, conversation_id)  # reuses the ownership check
        return await self._conversations.history(conversation_id)
