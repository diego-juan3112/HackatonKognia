"""Assemble and compile the conversation graph.

    intake -> classify_intent -> collect_data -> route -+-> retrieve_context -> respond -> END
                                                        |
                                                        +-> respond -> END

Every node here is a generic capability from AGENTS.md section 3. Adapting to
the real challenge domain means supplying a different DomainSpec, and -- if the
flow genuinely needs it -- adding a node. The nodes below do not get edited.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from models.domain_config import DomainSpec
from models.ports import LLMPort, RetrievalPort
from services.graph.edges import after_route
from services.graph.nodes.classify_intent import make_classify_intent
from services.graph.nodes.collect_data import make_collect_data
from services.graph.nodes.intake import make_intake
from services.graph.nodes.respond import make_respond
from services.graph.nodes.retrieve_context import make_retrieve_context
from services.graph.nodes.route import make_route
from services.graph.state import ConversationState


def build_graph(
    llm: LLMPort,
    retriever: RetrievalPort,
    domain: DomainSpec,
    top_k: int = 4,
    checkpointer: MemorySaver | None = None,
):
    """Compile the graph.

    The checkpointer gives per-``thread_id`` memory. MemorySaver is enough for
    the event; a persistent one can be swapped in without touching the nodes.
    """
    graph = StateGraph(ConversationState)

    graph.add_node("intake", make_intake())
    graph.add_node("classify_intent", make_classify_intent(llm, domain))
    graph.add_node("collect_data", make_collect_data(llm, domain))
    graph.add_node("route", make_route(domain))
    graph.add_node("retrieve_context", make_retrieve_context(retriever, top_k=top_k))
    graph.add_node("respond", make_respond(llm, domain))

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "classify_intent")
    graph.add_edge("classify_intent", "collect_data")
    graph.add_edge("collect_data", "route")

    # The only branch in the graph, and it is a pure function of state.
    graph.add_conditional_edges(
        "route",
        after_route,
        {"retrieve_context": "retrieve_context", "respond": "respond"},
    )

    graph.add_edge("retrieve_context", "respond")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())
