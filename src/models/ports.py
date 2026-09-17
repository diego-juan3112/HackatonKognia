"""The swappable ports of AGENTS.md section 5.

These Protocols live in ``models/`` rather than in ``services/`` on purpose.
``models/`` is the transversal layer (AGENTS.md section 2), so both
``services/`` and ``integrations/`` can import it without anything having to
depend upwards. If the ports lived in ``services/``, every adapter would have
to import the core and the dependency rule would break.

Hard rule these exist to enforce: swapping a provider must mean editing only
``integrations/``. Nothing here mentions Cartesia, Deepgram, OpenAI, Chroma or
any other vendor, and no vendor SDK type appears in a signature.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from models.conversation import AudioChunk, SpeechChunk, Utterance, VisemeFrame
from models.retrieval import Document, RetrievedChunk

# ---------------------------------------------------------------------------
# LLM -- already decided (Azure OpenAI / OpenAI), so we reuse LangChain's
# stable interface instead of inventing our own wrapper.
# ---------------------------------------------------------------------------

LLMPort = BaseChatModel
ToolPort = BaseTool


# ---------------------------------------------------------------------------
# Retrieval -- provider undecided (AGENTS.md section 6).
# ---------------------------------------------------------------------------


@runtime_checkable
class RetrievalPort(Protocol):
    """Ingest documents and answer "what context is relevant to this turn?"."""

    def index(self, documents: Sequence[Document]) -> int:
        """Add or replace documents. Returns the number of chunks written."""
        ...

    def search(
        self,
        query: str,
        top_k: int = 4,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Return the most relevant chunks, best first."""
        ...

    def count(self) -> int:
        """Number of chunks currently indexed. Used by /health."""
        ...

    def reset(self) -> None:
        """Drop everything indexed. Used by tests and by re-ingestion."""
        ...


# ---------------------------------------------------------------------------
# Voice -- provider undecided (AGENTS.md section 1.1).
# Declared, deliberately unimplemented. Do not add a concrete adapter until
# the provider is chosen; AGENTS.md section 8 forbids it.
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
# Avatar -- provider undecided (AGENTS.md section 1.2).
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
