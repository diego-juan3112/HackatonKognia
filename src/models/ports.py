"""The swappable ports of docs/02-puertos.md (rule R-03).

These Protocols live in ``models/`` rather than in ``services/`` on purpose.
``models/`` is the transversal layer (rule R-01), so both ``services/`` and
``integrations/`` can import it without anything having to depend upwards.

Hard rule these exist to enforce: swapping a provider must mean editing only
``integrations/``. Nothing here mentions OpenAI, Gemini, Cartesia or Socrata,
and no vendor SDK type appears in a signature.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from models.analysis import AffectLabels, AnalysisResult, UtteranceAnalysisRequest
from models.ips import Deadline, QueryResult
from models.voice import (
    EngineSetup,
    FeedbackEvent,
    RealtimeSession,
    RealtimeSessionRequest,
    SpeechSession,
    SpeechSessionRequest,
)


@runtime_checkable
class DatasetPort(Protocol):
    """Run a read-only query that ``services/ips`` already built (R-23).

    The adapter executes, retries within the deadline and labels its cache;
    it never decides grain, units or warnings -- services/ does (R-22).
    Raises ``models.ips.DatasetUnavailable`` when the source cannot answer.
    """

    async def query(self, soql: str, *, deadline: Deadline, bypass_cache: bool = False) -> QueryResult:
        ...


@runtime_checkable
class RealtimeSessionPort(Protocol):
    """Mint an ephemeral credential for one voice engine (R-28)."""

    engine: str
    model: str
    supports_text_only: bool

    async def create(self, req: RealtimeSessionRequest, setup: EngineSetup) -> RealtimeSession: ...


@runtime_checkable
class SpeechSessionPort(Protocol):
    """Mint a short synthesis-only token for the cloned voice (D-20)."""

    async def create(self, req: SpeechSessionRequest) -> SpeechSession: ...


@runtime_checkable
class AffectModelPort(Protocol):
    """One structured affect estimate, from text or from audio (docs/10 section 6)."""

    name: str
    supports_audio: bool

    async def estimate(
        self, text: str, audio_wav: bytes | None, *, timeout_s: float, prosody: str | None = None
    ) -> AffectLabels: ...


@runtime_checkable
class AnalystPort(Protocol):
    async def analyze(self, req: UtteranceAnalysisRequest, audio_wav: bytes | None) -> AnalysisResult: ...


@runtime_checkable
class FeedbackPort(Protocol):
    async def record(self, event: FeedbackEvent) -> None: ...
