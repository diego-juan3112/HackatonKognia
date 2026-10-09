"""Cartesia synthesis token for the cloned voice (D-20, docs/08 section 15.3).

Measured 2026-10-09 with the team key: ``POST /access-token`` with
``Cartesia-Version: 2026-08-14``, ``grants.tts`` and 600 s -> 200 in 0.4-1.2 s,
body ``{"token"}`` only (we compute ``expires_at``); ``expires_in`` > 3600 -> 400.
The API key never reaches the browser (R-28).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from models.voice import ConnectInfo, ProviderUnavailable, SpeechSession, SpeechSessionRequest


class CartesiaSpeechSession:
    def __init__(self, *, api_key: str, voice_id: str, model: str, version: str, voice_label: str,
                 ttl_s: int = 600, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.model = model
        self._key = api_key
        self._voice_id = voice_id
        self._version = version
        self._label = voice_label
        self._ttl = min(ttl_s, 3600)
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._key and self._voice_id)

    async def create(self, req: SpeechSessionRequest) -> SpeechSession:
        if not self.configured:
            raise ProviderUnavailable("SYNTH_UNAVAILABLE", "La voz clonada no está configurada")
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=5.0) as c:
                r = await c.post("https://api.cartesia.ai/access-token",
                                 headers={"Authorization": f"Bearer {self._key}", "Cartesia-Version": self._version},
                                 json={"grants": {"tts": True}, "expires_in": self._ttl})
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("SYNTH_UNAVAILABLE", f"Cartesia: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise ProviderUnavailable("SYNTH_UNAVAILABLE", f"Cartesia: HTTP {r.status_code}")
        token = r.json().get("token", "")
        expires_at = (datetime.now(UTC) + timedelta(seconds=self._ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return SpeechSession(
            synth="cartesia", model=self.model,
            connect=ConnectInfo(
                url=f"wss://api.cartesia.ai/tts/websocket?cartesia_version={self._version}&access_token={token}",
                token=token, expires_at=expires_at),
            config={"audio": {"encoding": "pcm_s16le", "sample_rate": 24000, "container": "raw"},
                    "voice_id": self._voice_id, "language": "es", "timestamps": True},
            voice_label=self._label,
        )
