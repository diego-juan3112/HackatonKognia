"""acoustic_affect: how the voice sounds (audio + local prosody), only with consent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from models.ports import AffectModelPort
from services.analyst.state import AnalystState

log = logging.getLogger(__name__)


def make_acoustic_affect(model: AffectModelPort | None) -> Callable[[AnalystState], Awaitable[dict]]:
    async def acoustic_affect(state: AnalystState) -> dict:
        audio = state.get("audio")
        if not audio or model is None or not model.supports_audio:
            return {"voice_labels": None, "voice_model": None}
        remaining = state["deadline"].remaining() - 0.1
        if remaining <= 0.2:
            return {"voice_labels": None, "voice_model": None}
        try:
            labels = await asyncio.wait_for(
                model.estimate(state["req"].text, audio, timeout_s=remaining, prosody=state.get("prosody")),
                timeout=remaining)
            return {"voice_labels": labels, "voice_model": model.name}
        except Exception as exc:  # noqa: BLE001
            log.warning("acoustic affect via %s failed: %s", model.name, type(exc).__name__)
            return {"voice_labels": None, "voice_model": None}

    return acoustic_affect
