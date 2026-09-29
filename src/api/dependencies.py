"""Composition root.

Everything is assembled here, once, during the FastAPI lifespan. Nothing is
built at import time, so importing the app needs no database, no credentials
and no model download -- which is what lets the test suite import it freely.

This is also the only file in ``api/`` allowed to name ``integrations``: it
wires the object graph. Request handlers receive the assembled container, so
the layer rule of AGENTS.md section 2 still holds at call time.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request

from config import Settings, get_settings
from integrations.db.conversation_repository import PostgresConversationRepository
from integrations.db.migrations import pending
from integrations.db.pool import create_pool
from integrations.db.user_repository import PostgresUserRepository
from integrations.llm.factory import build_llm
from integrations.retrieval.embeddings import build_embedder
from integrations.retrieval.pgvector_retriever import PgVectorRetriever
from models.auth import User
from models.domain_config import DomainSpec
from models.ports import ConversationRepositoryPort, LLMPort, RetrievalPort, UserRepositoryPort
from platform_compat import assert_event_loop_is_usable
from services.auth_service import AuthService, InvalidSession
from services.chat_service import ChatService
from services.domain_loader import load_domain
from services.graph.builder import build_graph


@dataclass(slots=True)
class Container:
    """Everything the request handlers need, assembled once."""

    settings: Settings
    domain: DomainSpec
    llm: LLMPort
    retriever: RetrievalPort
    users: UserRepositoryPort
    conversations: ConversationRepositoryPort
    auth: AuthService
    chat: ChatService
    pool: Any
    checkpointer: Any
    _checkpointer_cm: Any = None


async def build_container(settings: Settings | None = None) -> Container:
    """Open the database, build the graph, wire the services.

    Awaitable because opening the pool and setting up the checkpointer are I/O.
    Call ``shutdown_container`` to release both.
    """
    settings = settings or get_settings()

    # Fails here with an actionable message rather than as a pool timeout.
    assert_event_loop_is_usable()

    # Fail at startup, with the fix spelled out, rather than with an opaque
    # "relation does not exist" in the middle of someone's first request.
    todo = await asyncio.to_thread(pending, settings.database_url)
    if todo:
        raise RuntimeError(
            f"La base tiene migraciones pendientes: {', '.join(todo)}. "
            f"Corre:  python -m scripts.migrate"
        )

    pool = create_pool(
        settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    await pool.open(wait=True)

    # LangGraph owns these tables and creates them itself; they are not in our
    # migrations on purpose, so the library can evolve its own schema.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    checkpointer_cm = AsyncPostgresSaver.from_conn_string(settings.database_url)
    checkpointer = await checkpointer_cm.__aenter__()
    await checkpointer.setup()

    domain = load_domain(settings.domain_config_path)
    llm = build_llm(settings)
    retriever = PgVectorRetriever(
        pool=pool,
        embedder=build_embedder(settings.embedding_model),
    )
    graph = build_graph(
        llm=llm,
        retriever=retriever,
        domain=domain,
        top_k=settings.retrieval_top_k,
        checkpointer=checkpointer,
    )

    users = PostgresUserRepository(pool)
    conversations = PostgresConversationRepository(pool)

    return Container(
        settings=settings,
        domain=domain,
        llm=llm,
        retriever=retriever,
        users=users,
        conversations=conversations,
        auth=AuthService(users, session_ttl_hours=settings.session_ttl_hours),
        chat=ChatService(graph=graph, conversations=conversations, domain=domain),
        pool=pool,
        checkpointer=checkpointer,
        _checkpointer_cm=checkpointer_cm,
    )


async def shutdown_container(container: Container) -> None:
    """Release the pool and the checkpointer connection."""
    if container._checkpointer_cm is not None:
        await container._checkpointer_cm.__aexit__(None, None, None)
    if container.pool is not None:
        await container.pool.close()


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(status_code=503, detail="La aplicacion aun no termina de arrancar.")
    return container


async def current_user(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    container: Container = Depends(get_container),
) -> User:
    """Resolve the caller from the session header.

    Reminder: the session proves only that somebody typed a cedula, not that
    they own it. See services/auth_service.py.
    """
    if not x_session_id:
        raise HTTPException(status_code=401, detail="Falta el header X-Session-Id.")
    try:
        session_id = UUID(x_session_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="X-Session-Id no es un UUID valido.") from None

    try:
        return await container.auth.user_of(session_id)
    except InvalidSession as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
