"""Intake: normalise the incoming turn.

Generic capability. It must not inspect *what* the user said beyond counting
the turn -- interpreting content is the classifier's job.
"""

from __future__ import annotations

from collections.abc import Callable

from services.graph.state import ConversationState


def make_intake() -> Callable[[ConversationState], dict]:
    """Build the intake node."""

    def intake(state: ConversationState) -> dict:
        turn_count = state.get("turn_count", 0) + 1
        # A new turn invalidates the previous turn's retrieval and routing,
        # so they are cleared rather than carried forward stale.
        return {
            "turn_count": turn_count,
            "retrieved": [],
            "route": None,
        }

    return intake
