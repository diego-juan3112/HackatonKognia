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


class UserContext(TypedDict, total=False):
    """Who the agent is talking to.

    Set by chat_service from the authenticated session on every turn -- never
    by the model (AGENTS.md section 8). The cedula is already masked: this state
    is persisted by the checkpointer, and nothing in the graph needs the full
    number.
    """

    user_id: str
    display_name: str | None
    cedula_last4: str


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

    # The person on the other side, from the session. None for anonymous turns.
    user: UserContext | None


def initial_state(message: str, user: UserContext | None = None) -> ConversationState:
    """Build the state for a fresh turn."""
    from langchain_core.messages import HumanMessage

    return ConversationState(
        messages=[HumanMessage(content=message)],
        intent=None,
        collected={},
        missing_fields=[],
        route=None,
        retrieved=[],
        user=user,
    )
