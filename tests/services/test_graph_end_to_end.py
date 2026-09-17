"""The full graph, exercised offline.

Each test walks a different branch of the graph, which is what proves the
pipeline is wired: intake -> classify -> collect -> route -> (retrieve) ->
respond.
"""

from __future__ import annotations

from models.conversation import RouteDecision
from services.graph.builder import build_graph
from services.graph.state import initial_state


def _run(graph, message: str, thread: str = "t"):
    return graph.invoke(
        initial_state(message),
        config={"configurable": {"thread_id": thread}},
    )


def test_answer_branch_quotes_retrieved_context(llm, retriever, domain):
    """The happy path: retrieval must actually feed the response."""
    graph = build_graph(llm=llm, retriever=retriever, domain=domain)

    result = _run(graph, "cual es el horario de atencion")

    assert result["route"] == RouteDecision.ANSWER
    assert result["retrieved"], "retrieve_context did not run or found nothing"
    reply = result["messages"][-1].content
    # The fake model echoes the context it was given, so seeing corpus content
    # in the reply is direct evidence that retrieval reached respond.
    assert "8:00" in reply or "17:00" in reply


def test_collect_branch_asks_instead_of_answering(llm, retriever, domain):
    """An intent with a required field must produce a question, not an answer."""
    graph = build_graph(llm=llm, retriever=retriever, domain=domain)

    result = _run(graph, "quiero saber como va mi solicitud radicada")

    assert result["intent"] == "estado_solicitud"
    assert result["route"] == RouteDecision.COLLECT
    assert result["missing_fields"] == ["numero_radicado"]
    assert "radicado" in result["messages"][-1].content.lower()
    # The collect branch must not spend a retrieval call.
    assert result["retrieved"] == []


def test_escalate_branch_uses_the_domain_message(llm, retriever, domain):
    graph = build_graph(llm=llm, retriever=retriever, domain=domain)

    result = _run(graph, "esto es un fraude y voy a poner una demanda")

    assert result["route"] == RouteDecision.ESCALATE
    assert "asesor" in result["messages"][-1].content.lower()


def test_empty_index_does_not_break_the_graph(llm, empty_retriever, domain):
    """A demo with nothing ingested must still answer, not crash."""
    graph = build_graph(llm=llm, retriever=empty_retriever, domain=domain)

    result = _run(graph, "cual es el horario de atencion")

    assert result["retrieved"] == []
    assert result["messages"][-1].content


def test_thread_memory_accumulates(llm, retriever, domain):
    graph = build_graph(llm=llm, retriever=retriever, domain=domain)

    _run(graph, "cual es el horario", thread="same")
    second = _run(graph, "y los canales de contacto", thread="same")

    assert second["turn_count"] == 2
    assert len(second["messages"]) >= 4
