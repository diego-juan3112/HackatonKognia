"""Slot filling against a declared field schema.

Generic capability: the node asks "which declared fields are still missing?".
It has no idea whether a field is a policy number or an account balance --
those are names in the domain YAML.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from models.domain_config import DomainSpec
from models.ports import LLMPort
from services.graph.state import ConversationState

_PROMPT = """Extract the following fields from the conversation, if present.

Fields: {fields}

Reply with a JSON object using exactly those keys. Omit any key you cannot
fill from what the user actually said. Never invent a value."""


def _conversation_text(state: ConversationState) -> str:
    parts = []
    for message in state.get("messages", []):
        role = "user" if isinstance(message, HumanMessage) else "agent"
        parts.append(f"{role}: {message.content}")
    return "\n".join(parts)


def _extract(llm: LLMPort, field_names: list[str], conversation: str) -> dict:
    system = _PROMPT.format(fields=", ".join(field_names))
    response = llm.invoke(
        [SystemMessage(content=system), HumanMessage(content=conversation)]
    )
    try:
        parsed = json.loads(str(response.content))
    except (json.JSONDecodeError, TypeError):
        # A model that does not return JSON simply yields nothing this turn;
        # the field stays missing and the agent asks for it.
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {k: v for k, v in parsed.items() if k in field_names and v not in (None, "")}


def make_collect_data(llm: LLMPort, domain: DomainSpec) -> Callable[[ConversationState], dict]:
    """Build the slot-filling node."""

    def collect_data(state: ConversationState) -> dict:
        intent = domain.intent(state.get("intent"))
        if intent is None or not intent.required_fields:
            return {"missing_fields": []}

        collected = dict(state.get("collected", {}))
        required = [f for f in intent.required_fields if f.required]
        pending = [f.name for f in required if f.name not in collected]

        if pending:
            collected.update(_extract(llm, pending, _conversation_text(state)))

        missing = [f.name for f in required if f.name not in collected]
        return {"collected": collected, "missing_fields": missing}

    return collect_data
