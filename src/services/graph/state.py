"""The state that travels through the graph.

Every field here is generic. There is no field named after a business domain,
and there never should be: domain-specific data lives inside ``collected``,
keyed by the field names declared in the domain YAML.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from models.conversation import RouteDecision
from models.retrieval import RetrievedChunk


class ConversationState(TypedDict, total=False):
    """Shared state for one conversation thread."""

    # Conversation history. ``add_messages`` appends instead of replacing.
    messages: Annotated[list[BaseMessage], add_messages]

    # Set by classify_intent; a name from the domain's intent catalogue.
    intent: str | None

    # Domain data gathered so far, keyed by FieldSpec.name.
    collected: dict[str, Any]

    # Declared-but-absent fields, computed by collect_data.
    missing_fields: list[str]

    # Set by the route node. Conditional edges read this and nothing else.
    route: RouteDecision | None

    # Context pulled by retrieve_context, consumed by respond.
    retrieved: list[RetrievedChunk]

    # How many user turns this thread has seen. Drives escalation rules.
    turn_count: int


def initial_state(message: str) -> ConversationState:
    """Build the state for a fresh turn."""
    from langchain_core.messages import HumanMessage

    return ConversationState(
        messages=[HumanMessage(content=message)],
        intent=None,
        collected={},
        missing_fields=[],
        route=None,
        retrieved=[],
    )
