"""text_affect: affect from the words, with the D-10 fallback chain fast -> deep."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

from models.ports import AffectModelPort
from services.analyst.state import AnalystState

log = logging.getLogger(__name__)


def make_text_affect(chain: Sequence[AffectModelPort]) -> Callable[[AnalystState], Awaitable[dict]]:
    async def text_affect(state: AnalystState) -> dict:
        deadline = state["deadline"]
        for model in chain:
            remaining = deadline.remaining() - 0.1
            if remaining <= 0.2:
                break
            try:
                labels = await asyncio.wait_for(
                    model.estimate(state["req"].text, None, timeout_s=remaining), timeout=remaining)
                return {"text_labels": labels, "text_model": model.name}
            except Exception as exc:  # noqa: BLE001 -- any failure means "try the next profile"
                log.warning("text affect via %s failed: %s", model.name, type(exc).__name__)
        return {"text_labels": None, "text_model": None}  # -> uncertain, never a stale label

    return text_affect
