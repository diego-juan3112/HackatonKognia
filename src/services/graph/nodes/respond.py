"""Response generation.

Handles the three terminal shapes a turn can take. Two of them (collect and
escalate) are deterministic and need no model call at all -- that keeps the
demo cheap and the tests exact.
"""

from __future__ import annotations

from collections.abc import Callable

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


def make_respond(llm: LLMPort, domain: DomainSpec) -> Callable[[ConversationState], dict]:
    """Build the response node."""

    def respond(state: ConversationState) -> dict:
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

        prompt = [SystemMessage(content=domain.system_prompt)]
        prompt.append(SystemMessage(content=_CONTEXT_BLOCK.format(context=context)))
        prompt.extend(m for m in state.get("messages", []) if isinstance(m, HumanMessage))

        response = llm.invoke(prompt)
        return {"messages": [AIMessage(content=str(response.content))]}

    return respond
