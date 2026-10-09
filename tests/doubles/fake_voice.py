"""Doubles for the Reto 01 voice ports (R-09): realtime, speech, affect, analyst, feedback."""

from __future__ import annotations

import asyncio

from models.analysis import AffectLabels, AnalysisResult, UtteranceAnalysisRequest
from models.voice import (
    ConnectInfo,
    EngineSetup,
    FeedbackEvent,
    ProviderUnavailable,
    RealtimeSession,
    RealtimeSessionRequest,
    SpeechSession,
    SpeechSessionRequest,
)


class FakeRealtimeSession:
    def __init__(self, engine: str, *, supports_text_only: bool, fail: str | None = None) -> None:
        self.engine = engine
        self.model = f"fake-{engine}"
        self.supports_text_only = supports_text_only
        self.configured = True
        self.fail = fail
        self.setups: list[EngineSetup] = []

    async def create(self, req: RealtimeSessionRequest, setup: EngineSetup) -> RealtimeSession:
        if self.fail:
            raise ProviderUnavailable(self.fail, "simulated")
        self.setups.append(setup)
        return RealtimeSession(engine=self.engine, model=self.model,  # type: ignore[arg-type]
                               connect=ConnectInfo(url=f"wss://fake/{self.engine}", token="ek_fake",
                                                   expires_at="2026-10-09T16:00:00Z"),
                               config={"voice_mode": setup.voice_mode}, instructions_version=setup.instructions_version)


class FakeSpeechSession:
    configured = True

    async def create(self, req: SpeechSessionRequest) -> SpeechSession:
        return SpeechSession(synth="fake", model="fake-tts",
                             connect=ConnectInfo(url="wss://fake/tts", token="tok", expires_at="2026-10-09T16:00:00Z"),
                             config={"voice_id": "v1", "language": "es"}, voice_label="Voz de prueba")


class FakeAffectModel:
    """Scripted labels; can fail or be slow to exercise the fallback and the deadline."""

    def __init__(self, name: str, labels: AffectLabels | None = None, *, supports_audio: bool = False,
                 fail: bool = False, delay_s: float = 0.0) -> None:
        self.name = name
        self.supports_audio = supports_audio
        self.labels = labels or AffectLabels(sentiment="neutral", emotion="neutral", state_hint="desconocido")
        self.fail = fail
        self.delay_s = delay_s
        self.calls: list[tuple[str, bool]] = []

    async def estimate(self, text: str, audio_wav: bytes | None, *, timeout_s: float,
                       prosody: str | None = None) -> AffectLabels:
        self.calls.append((text, audio_wav is not None))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.fail:
            raise RuntimeError("simulated provider failure")
        return self.labels


class FakeAnalyst:
    def __init__(self, result: AnalysisResult) -> None:
        self.result = result
        self.requests: list[tuple[UtteranceAnalysisRequest, bytes | None]] = []

    async def analyze(self, req: UtteranceAnalysisRequest, audio_wav: bytes | None) -> AnalysisResult:
        self.requests.append((req, audio_wav))
        return self.result


class FakeFeedback:
    def __init__(self) -> None:
        self.events: list[FeedbackEvent] = []

    async def record(self, event: FeedbackEvent) -> None:
        self.events.append(event)
