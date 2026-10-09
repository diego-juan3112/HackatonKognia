"""style_policy: deterministic style decision with smoothing (config/style_policy.yaml)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from services.analyst.state import AnalystState
from services.analyst.style import StylePolicy


def make_style_policy(policy: StylePolicy) -> Callable[[AnalystState], Awaitable[dict]]:
    async def style_policy(state: AnalystState) -> dict:
        req = state["req"]
        style = policy.decide(state["affect"], explicit_preference=state.get("explicit_preference"),
                              history=req.affect_history, current=req.current_style, turn_index=req.turn_index)
        return {"style": style}

    return style_policy
