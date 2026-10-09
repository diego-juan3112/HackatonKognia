"""prepare: explicit signals (deterministic) and local prosody, before any model call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from services.analyst import prosody
from services.analyst.state import AnalystState
from services.analyst.style import StylePolicy


def make_prepare(policy: StylePolicy) -> Callable[[AnalystState], Awaitable[dict]]:
    async def prepare(state: AnalystState) -> dict:
        req = state["req"]
        audio = state.get("audio") if req.voice_consent else None  # R-26: no consent, no voice analysis
        p = prosody.measure(audio, req.text) if audio else None
        if p is not None and p.duration_s < 1.0:
            audio, p = None, None  # docs/10: audio < 1 s -> text only
        return {
            "audio": audio,
            "prosody": p.describe() if p else None,
            "explicit_preference": policy.detect_preference(req.text) or req.tone_preference,
            "explicit_state": policy.detect_state(req.text),
        }

    return prepare
