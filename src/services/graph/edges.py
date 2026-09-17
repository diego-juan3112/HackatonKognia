"""Conditional edges.

AGENTS.md section 8: the graph controls the flow, never the model. Every
function here is a pure function of state -- no LLM call, no I/O, no clock.
That is what makes the routing testable and predictable, and it is the main
reason this graph is hand-built instead of using ``create_react_agent`` (where
the model decides the loop via tool calls).
"""

from __future__ import annotations

from typing import Literal

from models.conversation import RouteDecision
from services.graph.state import ConversationState


def after_route(state: ConversationState) -> Literal["retrieve_context", "respond"]:
    """Decide whether the turn needs context before answering.

    Reads ``route`` and nothing else. The route node already applied the
    domain rules; this function only maps a decision to a node name.
    """
    if state.get("route") == RouteDecision.ANSWER:
        return "retrieve_context"
    return "respond"
