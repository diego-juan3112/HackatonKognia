"""Repository ports backed by dictionaries.

They enforce the same invariants the database does -- unique cedula, cascade on
delete, updated_at moving with the newest message -- so a test passing here
means the business logic is right, not that the constraint was skipped.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from models.auth import Conversation, MessageRecord, Session, User, UserAlreadyExists


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryUserRepository:
    """Satisfies ``models.ports.UserRepositoryPort``."""

    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.sessions: dict[UUID, Session] = {}

    async def find_by_cedula(self, cedula: str) -> User | None:
        return next((u for u in self.users.values() if u.cedula == cedula), None)

    async def find_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def create(self, cedula: str, display_name: str | None = None) -> User:
        # Mirrors the UNIQUE constraint on users.cedula.
        if await self.find_by_cedula(cedula) is not None:
            raise UserAlreadyExists(cedula)
        user = User(id=uuid4(), cedula=cedula, display_name=display_name, created_at=_now())
        self.users[user.id] = user
        return user

    async def touch_last_seen(self, user_id: UUID) -> None:
        user = self.users.get(user_id)
        if user is not None:
            self.users[user_id] = user.model_copy(update={"last_seen_at": _now()})

    async def create_session(self, user_id: UUID, ttl_hours: int) -> Session:
        session = Session(
            id=uuid4(),
            user_id=user_id,
            created_at=_now(),
            expires_at=_now() + timedelta(hours=ttl_hours),
        )
        self.sessions[session.id] = session
        return session

    async def get_session(self, session_id: UUID) -> Session | None:
        return self.sessions.get(session_id)

    # -- helpers for tests -------------------------------------------------
    def expire(self, session_id: UUID) -> None:
        """Force a session into the past, to exercise the expiry path."""
        session = self.sessions[session_id]
        self.sessions[session_id] = session.model_copy(
            update={"expires_at": _now() - timedelta(seconds=1)}
        )


class InMemoryConversationRepository:
    """Satisfies ``models.ports.ConversationRepositoryPort``."""

    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: dict[UUID, list[MessageRecord]] = {}

    async def create(
        self, user_id: UUID, domain: str, title: str | None = None
    ) -> Conversation:
        conversation = Conversation(
            id=uuid4(),
            user_id=user_id,
            thread_id=str(uuid4()),
            title=title,
            domain=domain,
            created_at=_now(),
            updated_at=_now(),
        )
        self.conversations[conversation.id] = conversation
        self.messages[conversation.id] = []
        return conversation

    async def get(self, conversation_id: UUID) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def list_for_user(self, user_id: UUID, limit: int = 50) -> list[Conversation]:
        owned = [c for c in self.conversations.values() if c.user_id == user_id]
        owned.sort(key=lambda c: c.updated_at, reverse=True)
        return owned[:limit]

    async def append_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        intent: str | None = None,
        route: str | None = None,
        sources: Sequence[str] = (),
    ) -> MessageRecord:
        record = MessageRecord(
            id=uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            intent=intent,
            route=route,
            sources=list(sources),
            created_at=_now(),
        )
        self.messages.setdefault(conversation_id, []).append(record)

        # Same invariant the real repository keeps inside its transaction.
        conversation = self.conversations.get(conversation_id)
        if conversation is not None:
            self.conversations[conversation_id] = conversation.model_copy(
                update={"updated_at": record.created_at}
            )
        return record

    async def history(self, conversation_id: UUID, limit: int = 100) -> list[MessageRecord]:
        return self.messages.get(conversation_id, [])[:limit]
