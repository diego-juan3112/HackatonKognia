"""The swappable ports of docs/02-puertos.md (rule R-03).

These Protocols live in ``models/`` rather than in ``services/`` on purpose.
``models/`` is the transversal layer (rule R-01), so both
``services/`` and ``integrations/`` can import it without anything having to
depend upwards. If the ports lived in ``services/``, every adapter would have
to import the core and the dependency rule would break.

Hard rule these exist to enforce: swapping a provider must mean editing only
``integrations/``. Nothing here mentions Gemini, Cartesia, Deepgram, pgvector or
any other vendor, and no vendor SDK type appears in a signature.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from models.auth import Conversation, MessageRecord, Session, User
from models.conversation import AudioChunk, SpeechChunk, Utterance, VisemeFrame
from models.retrieval import Document, RetrievedChunk

# ---------------------------------------------------------------------------
# LLM -- the provider is decided (see integrations/llm), so we reuse LangChain's
# stable interface instead of inventing our own wrapper.
# ---------------------------------------------------------------------------

LLMPort = BaseChatModel
ToolPort = BaseTool


# ---------------------------------------------------------------------------
# Retrieval -- provider undecided (docs/04-rag.md).
# ---------------------------------------------------------------------------


@runtime_checkable
class RetrievalPort(Protocol):
    """Ingest documents and answer "what context is relevant to this turn?".

    Asynchronous because the backing store is PostgreSQL behind an async pool,
    and a blocking call here would stall FastAPI's event loop for every other
    request in flight.
    """

    async def index(self, documents: Sequence[Document]) -> int:
        """Add or replace documents. Returns the number of chunks written."""
        ...

    async def search(
        self,
        query: str,
        top_k: int = 4,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Return the most relevant chunks, best first."""
        ...

    async def count(self) -> int:
        """Number of chunks currently indexed. Used by /health."""
        ...

    async def reset(self) -> None:
        """Drop everything indexed. Used by tests and by re-ingestion."""
        ...


# ---------------------------------------------------------------------------
# Persistence -- PostgreSQL is decided, but ``services/`` still must not import
# psycopg. These ports keep SQL inside ``integrations/db/`` so the business
# logic can be tested against in-memory doubles with no database running.
# ---------------------------------------------------------------------------


@runtime_checkable
class UserRepositoryPort(Protocol):
    """Identity storage."""

    async def find_by_cedula(self, cedula: str) -> User | None: ...

    async def find_by_id(self, user_id: UUID) -> User | None: ...

    async def create(self, cedula: str, display_name: str | None = None) -> User:
        """Register a new person. Raises if the cedula already exists."""
        ...

    async def touch_last_seen(self, user_id: UUID) -> None: ...

    async def create_session(self, user_id: UUID, ttl_hours: int) -> Session: ...

    async def get_session(self, session_id: UUID) -> Session | None:
        """Return the session regardless of expiry; the caller decides validity."""
        ...


@runtime_checkable
class ConversationRepositoryPort(Protocol):
    """Chat threads and their readable history."""

    async def create(self, user_id: UUID, domain: str, title: str | None = None) -> Conversation:
        ...

    async def get(self, conversation_id: UUID) -> Conversation | None: ...

    async def list_for_user(self, user_id: UUID, limit: int = 50) -> list[Conversation]: ...

    async def append_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        intent: str | None = None,
        route: str | None = None,
        sources: Sequence[str] = (),
    ) -> MessageRecord: ...

    async def history(self, conversation_id: UUID, limit: int = 100) -> list[MessageRecord]: ...


# ---------------------------------------------------------------------------
# Voice -- provider undecided (docs/00-contexto-y-decisiones.md section 3).
# Declared, deliberately unimplemented. Do not add a concrete adapter until
# the provider is chosen; rule R-08 forbids it.
# ---------------------------------------------------------------------------


@runtime_checkable
class VoicePort(Protocol):
    """Speech in, speech out. Streaming in both directions."""

    async def transcribe(self, audio: AsyncIterator[AudioChunk]) -> AsyncIterator[Utterance]:
        """Consume microphone audio, yield transcripts.

        Partial results carry ``is_final=False``; the last one for a turn
        carries ``is_final=True``.
        """
        ...

    async def synthesize(self, text: str, voice: str | None = None) -> AsyncIterator[SpeechChunk]:
        """Turn text into playable audio chunks."""
        ...

    async def aclose(self) -> None:
        """Release the connection or device held by the adapter."""
        ...


# ---------------------------------------------------------------------------
# Avatar -- provider undecided (docs/00-contexto-y-decisiones.md section 4).
# The backend's job is the lip-sync timeline and the session handle; the mesh
# and the renderer live in the frontend.
# ---------------------------------------------------------------------------


@runtime_checkable
class AvatarPort(Protocol):
    """Drive a 3D avatar in sync with synthesized speech."""

    async def open_session(self, session_id: str) -> Mapping[str, Any]:
        """Start a render session. Returns whatever handle the frontend needs."""
        ...

    async def visemes_for(self, speech: SpeechChunk) -> list[VisemeFrame]:
        """Produce lip-sync frames aligned to a speech chunk.

        A provider that emits visemes natively just forwards them; one that
        does not derives them from the audio inside this adapter.
        """
        ...

    async def close_session(self, session_id: str) -> None:
        ...
