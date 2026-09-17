"""Retrieval: pull relevant context for the current turn.

The node asks RetrievalPort for context. It does not know whether the answer
comes from Chroma, from pgvector or from a list in memory, and it never sees
an embedding.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import HumanMessage

from models.ports import RetrievalPort
from services.graph.state import ConversationState


def make_retrieve_context(
    retriever: RetrievalPort,
    top_k: int = 4,
) -> Callable[[ConversationState], dict]:
    """Build the retrieval node."""

    def retrieve_context(state: ConversationState) -> dict:
        query = ""
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                query = str(message.content)
                break

        if not query:
            return {"retrieved": []}

        return {"retrieved": retriever.search(query, top_k=top_k)}

    return retrieve_context
