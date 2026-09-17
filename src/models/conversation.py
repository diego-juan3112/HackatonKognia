"""Data shapes for a conversation turn, including voice and avatar payloads.

The voice and avatar types exist even though no provider is chosen yet (see
AGENTS.md sections 1.1 and 1.2). They are deliberately provider-neutral: the
day a provider is picked, its adapter translates into these types and nothing
above ``integrations/`` changes.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Utterance(BaseModel):
    """One thing somebody said, as text."""

    role: Role
    text: str
    is_final: bool = True


class AudioChunk(BaseModel):
    """A slice of raw audio.

    ``pcm`` stays bytes on purpose: base64, container formats and provider
    specific encodings are an adapter concern and must not leak upwards.
    """

    pcm: bytes
    sample_rate: int = 24_000
    channels: int = 1


class SpeechChunk(BaseModel):
    """Synthesized audio produced by a VoicePort, ready to play."""

    audio: AudioChunk
    text: str = ""


class VisemeFrame(BaseModel):
    """One lip-sync keyframe, aligned to the audio timeline.

    ``viseme_id`` follows the mouth-shape identifier of whichever provider is
    chosen; the mapping to a 3D blendshape lives in the avatar adapter.
    """

    viseme_id: int
    audio_offset_ms: int
    duration_ms: int = 0


class RouteDecision(StrEnum):
    """What the graph decided to do with the current turn."""

    ANSWER = "answer"
    COLLECT = "collect"
    ESCALATE = "escalate"


class TurnResult(BaseModel):
    """What the API hands back after one pass through the graph."""

    reply: str
    thread_id: str
    intent: str | None = None
    route: RouteDecision = RouteDecision.ANSWER
    missing_fields: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
