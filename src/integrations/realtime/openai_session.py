"""OpenAI Realtime credential (D-11, recipe verified in G2: docs/anexos/g2 section 4).

``POST /v1/realtime/client_secrets`` mints a single-use ``ek_…`` secret. The
browser opens ``wss://api.openai.com/v1/realtime?model=…`` with subprotocols
``["realtime", "openai-insecure-api-key." + ek]``. The secret does **not** lock
the configuration (the client could ``session.update``), so every tool call is
still validated server-side (R-23) and rate-limited (R-28).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from models.voice import ConnectInfo, EngineSetup, ProviderUnavailable, RealtimeSession, RealtimeSessionRequest


log = logging.getLogger(__name__)


class OpenAIRealtimeSession:
    engine = "openai"
    supports_text_only = True  # output_modalities ["text"] measured in G2 -> cloned voice

    def __init__(self, *, api_key: str, model: str, voice: str, transcribe_model: str, ttl_s: int = 600,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.model = model
        self._key = api_key
        self._voice = voice
        self._transcribe = transcribe_model
        self._ttl = ttl_s
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def create(self, req: RealtimeSessionRequest, setup: EngineSetup) -> RealtimeSession:
        if not self._key:
            raise ProviderUnavailable("ENGINE_CONNECT_FAILED", "OpenAI no está configurado")
        text_only = setup.voice_mode == "cloned"
        turn_detection = {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300,
                          "silence_duration_ms": 500, "create_response": True, "interrupt_response": True}
        audio: dict = {
            "input": {"format": {"type": "audio/pcm", "rate": 24000},
                      "transcription": {"model": self._transcribe, "language": "es"},
                      "turn_detection": turn_detection},
        }
        if not text_only:
            audio["output"] = {"format": {"type": "audio/pcm", "rate": 24000}, "voice": setup.voice or self._voice}
        body = {
            "expires_after": {"anchor": "created_at", "seconds": self._ttl},
            "session": {
                "type": "realtime", "model": self.model, "instructions": setup.instructions,
                "output_modalities": ["text"] if text_only else ["audio"], "audio": audio,
                "tools": [{"type": "function", "name": t.name, "description": t.description,
                           "parameters": t.parameters} for t in setup.tools],
                "tool_choice": "auto",
            },
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=8.0) as c:
                r = await c.post("https://api.openai.com/v1/realtime/client_secrets",
                                 headers={"Authorization": f"Bearer {self._key}"}, json=body)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("ENGINE_CONNECT_FAILED", f"OpenAI: {type(exc).__name__}") from exc
        if r.status_code == 429:
            raise ProviderUnavailable("ENGINE_QUOTA", "OpenAI: límite o cuota")
        if r.status_code != 200:
            log.warning("OpenAI client_secrets HTTP %s: %s", r.status_code, r.text[:300])
            raise ProviderUnavailable("ENGINE_CONNECT_FAILED", f"OpenAI: HTTP {r.status_code}")
        data = r.json()
        secret = data.get("value") or data.get("client_secret", {}).get("value")
        expires = data.get("expires_at") or data.get("client_secret", {}).get("expires_at")
        expires_at = datetime.fromtimestamp(int(expires), UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if expires else ""
        return RealtimeSession(
            engine="openai", model=self.model,
            connect=ConnectInfo(url=f"wss://api.openai.com/v1/realtime?model={self.model}",
                                protocols=["realtime", f"openai-insecure-api-key.{secret}"],
                                token=secret, expires_at=expires_at),
            config={"audio": {"input": {"encoding": "pcm16", "sample_rate": 24000},
                              "output": None if text_only else {"encoding": "pcm16", "sample_rate": 24000}},
                    "voice": None if text_only else (setup.voice or self._voice),
                    "voice_mode": "cloned" if text_only else "engine",
                    "turn_detection": turn_detection, "transcription_model": self._transcribe},
            instructions_version=setup.instructions_version,
        )
