"""Routing: the deterministic decision node.

This node contains no LLM call at all, by design. AGENTS.md section 8 forbids
the model from driving state transitions, so the decision is a pure function of
state plus the domain rules, and it is written into ``state["route"]`` where
the edge function can read it.

Precedence is explicit and ordered; the first rule that matches wins.
"""

from __future__ import annotations

from collections.abc import Callable

from models.conversation import RouteDecision
from models.domain_config import DomainSpec
from services.graph.state import ConversationState


def make_route(domain: DomainSpec) -> Callable[[ConversationState], dict]:
    """Build the routing node bound to a domain's rules."""

    def route(state: ConversationState) -> dict:
        intent = domain.intent(state.get("intent"))

        # 1. The domain marks this intent as always-escalate.
        if intent is not None and intent.escalate:
            return {"route": RouteDecision.ESCALATE}

        # 2. The conversation has dragged on past the configured limit.
        limit = domain.max_turns_before_escalation
        if limit and state.get("turn_count", 0) > limit:
            return {"route": RouteDecision.ESCALATE}

        # 3. Declared fields are still missing: ask instead of answering.
        if state.get("missing_fields"):
            return {"route": RouteDecision.COLLECT}

        # 4. Nothing blocking: go find context and answer.
        return {"route": RouteDecision.ANSWER}

    return route
