"""ConversationRepositoryPort over PostgreSQL.

Owns the readable history. The LangGraph checkpointer owns the graph's internal
state separately -- see docs/01-arquitectura.md section 6 for why both exist.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from models.auth import Conversation, MessageRecord

_CONVERSATION_COLS = "id, user_id, thread_id, title, domain, created_at, updated_at"
_MESSAGE_COLS = "id, conversation_id, role, content, intent, route, sources, created_at"


def _to_message(row: dict) -> MessageRecord:
    # sources is JSONB; psycopg gives it back already decoded, but a string can
    # arrive if the column was written outside this adapter.
    sources = row.get("sources") or []
    if isinstance(sources, str):
        sources = json.loads(sources)
    return MessageRecord(**{**row, "sources": list(sources)})


class PostgresConversationRepository:
    """Concrete adapter satisfying ``models.ports.ConversationRepositoryPort``."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def create(
        self, user_id: UUID, domain: str, title: str | None = None
    ) -> Conversation:
        # The thread_id is ours to choose; LangGraph only requires it be stable
        # and unique per conversation.
        thread_id = str(uuid4())
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"INSERT INTO conversations (user_id, thread_id, title, domain) "
                    f"VALUES (%s, %s, %s, %s) RETURNING {_CONVERSATION_COLS}",
                    (user_id, thread_id, title, domain),
                )
                row = await cur.fetchone()
        return Conversation(**row)

    async def get(self, conversation_id: UUID) -> Conversation | None:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"SELECT {_CONVERSATION_COLS} FROM conversations WHERE id = %s",
                    (conversation_id,),
                )
                row = await cur.fetchone()
        return Conversation(**row) if row else None

    async def list_for_user(self, user_id: UUID, limit: int = 50) -> list[Conversation]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"SELECT {_CONVERSATION_COLS} FROM conversations "
                    f"WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s",
                    (user_id, limit),
                )
                rows = await cur.fetchall()
        return [Conversation(**row) for row in rows]

    async def append_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        intent: str | None = None,
        route: str | None = None,
        sources: Sequence[str] = (),
    ) -> MessageRecord:
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        f"INSERT INTO messages "
                        f"(conversation_id, role, content, intent, route, sources) "
                        f"VALUES (%s, %s, %s, %s, %s, %s) RETURNING {_MESSAGE_COLS}",
                        (
                            conversation_id,
                            role,
                            content,
                            intent,
                            route,
                            json.dumps(list(sources)),
                        ),
                    )
                    row = await cur.fetchone()
                    # Same transaction: a conversation's updated_at must never
                    # disagree with its newest message.
                    await cur.execute(
                        "UPDATE conversations SET updated_at = now() WHERE id = %s",
                        (conversation_id,),
                    )
        return _to_message(row)

    async def history(self, conversation_id: UUID, limit: int = 100) -> list[MessageRecord]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"SELECT {_MESSAGE_COLS} FROM messages "
                    f"WHERE conversation_id = %s ORDER BY created_at LIMIT %s",
                    (conversation_id, limit),
                )
                rows = await cur.fetchall()
        return [_to_message(row) for row in rows]
