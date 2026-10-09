"""Gemini Live credential (D-11, recipe verified in G2: docs/anexos/g2 section 4).

``POST v1alpha/auth_tokens`` with the full ``bidiGenerateContentSetup``: the
token **locks** the configuration (model, instructions, tools). The browser opens
``…BidiGenerateContentConstrained?access_token=<name>`` and sends
``{"setup": {"model": …}}``. Gemini Live rejects text-only output (G2: 1007),
so a ``cloned`` request comes back as ``engine`` (docs/08 section 15.6).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx

from models.voice import ConnectInfo, EngineSetup, ProviderUnavailable, RealtimeSession, RealtimeSessionRequest

log = logging.getLogger(__name__)

_WS = ("wss://generativelanguage.googleapis.com/ws/"
       "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class GeminiLiveSession:
    engine = "gemini"
    supports_text_only = False

    def __init__(self, *, api_key: str, model: str, voice: str, ttl_s: int = 1800,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.model = model
        self._key = api_key
        self._voice = voice
        self._ttl = ttl_s
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def create(self, req: RealtimeSessionRequest, setup: EngineSetup) -> RealtimeSession:
        if not self._key:
            raise ProviderUnavailable("ENGINE_CONNECT_FAILED", "Gemini no está configurado")
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self._ttl)
        voice = setup.voice or self._voice
        body = {
            "uses": 1,
            "expireTime": _iso(expires),
            "newSessionExpireTime": _iso(now + timedelta(minutes=2)),
            "bidiGenerateContentSetup": {
                "model": f"models/{self.model}",
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
                "systemInstruction": {"parts": [{"text": setup.instructions}]},
                "tools": [{"functionDeclarations": [{"name": t.name, "description": t.description,
                                                     "parameters": t.parameters} for t in setup.tools]}],
                "inputAudioTranscription": {}, "outputAudioTranscription": {},
                "sessionResumption": {}, "contextWindowCompression": {"slidingWindow": {}},
            },
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=8.0) as c:
                r = await c.post("https://generativelanguage.googleapis.com/v1alpha/auth_tokens",
                                 headers={"x-goog-api-key": self._key}, json=body)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("ENGINE_CONNECT_FAILED", f"Gemini: {type(exc).__name__}") from exc
        if r.status_code == 429:
            raise ProviderUnavailable("ENGINE_QUOTA", "Gemini: límite o cuota")
        if r.status_code != 200:
            # Google's message names the offending field; without it a 400 is opaque.
            log.warning("Gemini auth_tokens HTTP %s: %s", r.status_code, r.text[:300])
            raise ProviderUnavailable("ENGINE_CONNECT_FAILED", f"Gemini: HTTP {r.status_code}")
        name = r.json().get("name", "")
        return RealtimeSession(
            engine="gemini", model=self.model,
            connect=ConnectInfo(url=f"{_WS}?access_token={name}", token=name, expires_at=_iso(expires)),
            config={"audio": {"input": {"encoding": "pcm16", "sample_rate": 16000},
                              "output": {"encoding": "pcm16", "sample_rate": 24000}},
                    "voice": voice, "voice_mode": "engine", "turn_detection": {"type": "server"},
                    "setup": {"model": f"models/{self.model}"}},
            instructions_version=setup.instructions_version,
        )
