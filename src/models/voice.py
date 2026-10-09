"""Session and credential contract for the voice app (docs/08 sections 3 and 15).

Provider names, URLs and payload shapes stay inside ``integrations/realtime``
(R-03); these types are what crosses the boundary.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from models.analysis import StyleDecision

CONTRACT_VERSION = "2026-10-09.2"

EngineId = Literal["openai", "gemini"]
VoiceMode = Literal["engine", "cloned"]


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locale: str = Field(default="es-CO", max_length=16)


class SessionToken(BaseModel):
    token: str
    expires_at: str


class ContextEnvelope(BaseModel):
    """Neutral context envelope (docs/10 section 3) sent when renewing or switching.

    The backend only turns it into text for the new session's instructions; it
    never trusts it as a source of figures.
    """

    model_config = ConfigDict(extra="ignore")

    # Field names follow web/src/voice/types.ts (ContextEnvelope).
    instructions_version: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = Field(default=None, max_length=4000)
    recent_turns: list[dict[str, Any]] = Field(default_factory=list, max_length=4)
    current_utterance: dict[str, Any] | None = None
    tool_results: list[dict[str, Any]] = Field(default_factory=list, max_length=5)
    allowed_tools: list[str] = Field(default_factory=list)


class RealtimeSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: EngineId
    conversation_id: str = Field(min_length=1, max_length=128)
    seed: ContextEnvelope | None = None
    style: StyleDecision | None = None
    locale: str = "es-CO"
    voice: str | None = Field(default=None, max_length=64)
    voice_mode: VoiceMode = "engine"


class ToolSpec(BaseModel):
    """A tool declaration in provider-neutral JSON Schema."""

    name: str
    description: str
    parameters: dict[str, Any]


class EngineSetup(BaseModel):
    """Everything the backend fixes when minting an engine credential."""

    instructions: str
    instructions_version: str
    tools: list[ToolSpec]
    voice: str | None = None
    voice_mode: VoiceMode = "engine"
    locale: str = "es-CO"


class ConnectInfo(BaseModel):
    url: str
    protocols: list[str] | None = None
    token: str
    expires_at: str


class RealtimeSession(BaseModel):
    contract: str = CONTRACT_VERSION
    engine: EngineId
    model: str
    connect: ConnectInfo
    config: dict[str, Any]
    instructions_version: str
    brief: dict[str, Any] | None = None


class SpeechSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(min_length=1, max_length=128)


class SpeechSession(BaseModel):
    contract: str = CONTRACT_VERSION
    synth: str
    model: str
    connect: ConnectInfo
    config: dict[str, Any]
    voice_label: str


class FeedbackEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1, max_length=128)
    kind: Literal["correction", "tone", "repeat"]
    text: str | None = Field(default=None, max_length=2000)
    state_version: int = Field(default=0, ge=0)
    category: Literal["ASR", "ENTITY", "UNSUPPORTED", "TOOL_FAILURE", "WRONG_AGGREGATE", "TONE"] | None = None


class VerifyAnswerRequest(BaseModel):
    """Body of ``POST /verify/answer``: the agent's text and the tool results of that turn."""

    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(max_length=8000)
    tool_results: list[dict[str, Any]] = Field(default_factory=list, max_length=10)


class ProviderUnavailable(Exception):
    """A credential provider failed or is not configured (maps to 503)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
