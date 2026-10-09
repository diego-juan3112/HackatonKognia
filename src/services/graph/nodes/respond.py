"""Response generation.

Handles the three terminal shapes a turn can take. Two of them (collect and
escalate) are deterministic and need no model call at all -- that keeps the
demo cheap and the tests exact.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from models.conversation import RouteDecision
from models.domain_config import DomainSpec
from models.ports import LLMPort
from services.graph.state import ConversationState

_CONTEXT_BLOCK = """Use the following context to answer. If the context does
not contain the answer, say so plainly instead of inventing one.

Context:
{context}"""


def _field_prompt(domain: DomainSpec, state: ConversationState) -> str:
    """Ask for the first missing field, using the wording from the YAML."""
    intent = domain.intent(state.get("intent"))
    missing = state.get("missing_fields", [])
    if intent is None or not missing:
        return "Necesito un dato mas para continuar."

    for field in intent.required_fields:
        if field.name == missing[0]:
            return field.prompt
    return f"Necesito este dato para continuar: {missing[0]}"


# Enough turns for the model to follow the thread, bounded so a long
# conversation does not grow the prompt (and the latency) without limit.
_HISTORY_WINDOW = 10


def _recent_history(state: ConversationState) -> list:
    """The last turns of the conversation, both sides, starting on a user turn.

    Earlier this sent only the user's messages, which reads to a real model as
    one person talking to themselves: it never saw what it had already
    answered. The window must start on a user turn for Gemini.
    """
    turns = [
        m for m in state.get("messages", []) if isinstance(m, (HumanMessage, AIMessage))
    ][-_HISTORY_WINDOW:]
    while turns and not isinstance(turns[0], HumanMessage):
        turns.pop(0)
    return turns


def _user_block(state: ConversationState) -> str:
    """Tell the model who it is talking to, if the session says so.

    Generic on purpose (rule R-02): it knows there is a person with a
    name, not what business they came for. Only the last four digits of the
    cedula ever reach the model -- a free-tier LLM prompt is no place for a
    full national ID number.
    """
    user = state.get("user") or {}
    lines = []
    if user.get("display_name"):
        lines.append(
            f"You are talking to {user['display_name']}, identified by the system "
            "from their session. Address them by name naturally; do not ask for it."
        )
    if user.get("cedula_last4"):
        lines.append(
            f"Their national ID ends in {user['cedula_last4']}. Never ask for, "
            "guess or repeat the full number."
        )
    return " ".join(lines)


def make_respond(
    llm: LLMPort, domain: DomainSpec
) -> Callable[[ConversationState], Awaitable[dict]]:
    """Build the response node."""

    async def respond(state: ConversationState) -> dict:
        route = state.get("route")

        if route == RouteDecision.ESCALATE:
            return {"messages": [AIMessage(content=domain.escalation_message)]}

        if route == RouteDecision.COLLECT:
            return {"messages": [AIMessage(content=_field_prompt(domain, state))]}

        # RouteDecision.ANSWER -- the only branch that spends a model call.
        retrieved = state.get("retrieved", [])
        context = "\n\n".join(
            f"[{item.source}]\n{item.text}" for item in retrieved
        ) or "(sin contexto recuperado)"

        # One system message, not several: Gemini takes a single system
        # instruction, and relying on the client to merge them is fragile.
        system_text = "\n\n".join(
            part
            for part in (
                domain.system_prompt,
                _user_block(state),
                _CONTEXT_BLOCK.format(context=context),
            )
            if part
        )
        prompt = [SystemMessage(content=system_text), *_recent_history(state)]

        response = await llm.ainvoke(prompt)
        # .text, not str(.content): in langchain-core 1.x a reply can be a list
        # of content blocks, and str() of that list is not the answer.
        return {"messages": [AIMessage(content=response.text)]}

    return respond
