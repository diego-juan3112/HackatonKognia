"""The routing rules are the heart of AGENTS.md section 8.

These tests exist to prove the model cannot move the state machine: every
assertion below runs the route node and the edge function with no LLM at all.
"""

from __future__ import annotations

from models.conversation import RouteDecision
from services.graph.edges import after_route
from services.graph.nodes.route import make_route
from services.graph.state import ConversationState


def test_escalate_intent_wins_over_everything(domain):
    route = make_route(domain)
    state = ConversationState(intent="reclamo_grave", missing_fields=["x"], turn_count=1)

    assert route(state)["route"] == RouteDecision.ESCALATE


def test_missing_fields_force_collection(domain):
    route = make_route(domain)
    state = ConversationState(
        intent="estado_solicitud", missing_fields=["numero_radicado"], turn_count=1
    )

    assert route(state)["route"] == RouteDecision.COLLECT


def test_clean_turn_answers(domain):
    route = make_route(domain)
    state = ConversationState(intent="horario", missing_fields=[], turn_count=1)

    assert route(state)["route"] == RouteDecision.ANSWER


def test_turn_limit_escalates(domain):
    domain.max_turns_before_escalation = 2
    route = make_route(domain)

    ongoing = ConversationState(intent="horario", missing_fields=[], turn_count=2)
    exceeded = ConversationState(intent="horario", missing_fields=[], turn_count=3)

    assert route(ongoing)["route"] == RouteDecision.ANSWER
    assert route(exceeded)["route"] == RouteDecision.ESCALATE


def test_edge_is_a_pure_function_of_state():
    """The edge reads `route` and nothing else."""
    assert after_route(ConversationState(route=RouteDecision.ANSWER)) == "retrieve_context"
    assert after_route(ConversationState(route=RouteDecision.COLLECT)) == "respond"
    assert after_route(ConversationState(route=RouteDecision.ESCALATE)) == "respond"
    # Absent route must not crash the graph; it degrades to answering.
    assert after_route(ConversationState()) == "respond"
