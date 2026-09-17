"""Intent classification against a configurable catalogue.

The node knows there *is* a catalogue; it never knows what is in it. The list
of intents comes from the DomainSpec, so switching business domain is a
configuration change.

Note the boundary set by AGENTS.md section 8: the LLM fills in ``intent``,
which is data. It does not choose the next node -- that is the route node plus
a pure edge function.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from models.domain_config import DomainSpec
from models.ports import LLMPort
from services.graph.state import ConversationState

_PROMPT = """You classify a user message into exactly one intent.

Available intents:
{catalogue}

Reply with the intent name only, nothing else. If none fits, reply exactly:
{fallback}"""


def _last_user_text(state: ConversationState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def make_classify_intent(llm: LLMPort, domain: DomainSpec) -> Callable[[ConversationState], dict]:
    """Build the classifier node bound to a model and a domain."""

    # Examples are part of the catalogue entry, not decoration: they are the
    # strongest signal a classifier gets, and the schema declares them.
    lines = []
    for intent in domain.intents:
        line = f"- {intent.name}: {intent.description}"
        if intent.examples:
            line += " Ejemplos: " + "; ".join(intent.examples)
        lines.append(line)

    system = _PROMPT.format(catalogue="\n".join(lines), fallback=domain.fallback_intent)

    def classify_intent(state: ConversationState) -> dict:
        text = _last_user_text(state)
        if not text:
            return {"intent": domain.fallback_intent}

        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=text)])
        raw = str(response.content).strip().lower()

        # Never trust the model to return a name verbatim: match it against the
        # catalogue and fall back rather than propagating an invented intent.
        for name in domain.intent_names:
            if name.lower() in raw:
                return {"intent": name}
        return {"intent": domain.fallback_intent}

    return classify_intent
