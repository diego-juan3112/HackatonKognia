"""API contract, exercised with in-memory adapters.

The app is assembled from doubles instead of the real container, so these tests
cover routing, status codes and auth enforcement without a database. The real
wiring is covered in tests/integration/.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from api.dependencies import Container
from api.main import app
from integrations.llm.fake_llm import FakeChatModel
from models.retrieval import Document
from services.auth_service import AuthService
from services.chat_service import ChatService
from services.domain_loader import load_domain
from services.graph.builder import build_graph
from tests.conftest import REPO_ROOT
from tests.doubles import (
    InMemoryConversationRepository,
    InMemoryRetriever,
    InMemoryUserRepository,
)


@pytest.fixture
async def container(settings) -> Container:
    domain = load_domain(REPO_ROOT / "config" / "domains" / "faq_demo.yaml")
    llm = FakeChatModel()

    retriever = InMemoryRetriever()
    await retriever.index(
        [
            Document(
                source="horarios.md",
                text="La atencion presencial es de lunes a viernes de 8:00 a 17:00.",
            )
        ]
    )

    users = InMemoryUserRepository()
    conversations = InMemoryConversationRepository()
    graph = build_graph(
        llm=llm, retriever=retriever, domain=domain, checkpointer=MemorySaver()
    )

    return Container(
        settings=settings,
        domain=domain,
        llm=llm,
        retriever=retriever,
        users=users,
        conversations=conversations,
        auth=AuthService(users, session_ttl_hours=12),
        chat=ChatService(graph=graph, conversations=conversations, domain=domain),
        pool=None,
        checkpointer=None,
    )


@pytest.fixture
def client(container, monkeypatch):
    async def _fake_build():
        return container

    async def _fake_shutdown(_):
        return None

    monkeypatch.setattr("api.main.build_container", _fake_build)
    monkeypatch.setattr("api.main.shutdown_container", _fake_shutdown)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session_id(client) -> str:
    body = client.post("/auth/identify", json={"cedula": "1053812345"}).json()
    return body["session_id"]


def test_importing_the_app_needs_no_database():
    """Regression: the container must never be built at import time."""
    assert app.title.startswith("Kognia")


def test_health_reports_what_is_wired(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["model_provider"] == "fake"
    assert body["domain"] == "faq_demo"
    assert body["indexed_chunks"] >= 1
    # The password must never appear in an operational endpoint.
    assert "***" in body["database_url"] or "@" not in body["database_url"]


# --- auth ------------------------------------------------------------------


def test_identify_returns_a_session(client):
    body = client.post("/auth/identify", json={"cedula": "1.053.812.345"}).json()

    assert body["cedula"] == "1053812345", "debe normalizar la cedula"
    assert body["session_id"]
    assert body["user_id"]


def test_malformed_cedula_is_rejected(client):
    assert client.post("/auth/identify", json={"cedula": "abc"}).status_code == 422


def test_chat_without_session_header_is_rejected(client):
    response = client.post("/chat", json={"message": "hola"})
    assert response.status_code == 401


def test_chat_with_garbage_session_is_rejected(client):
    response = client.post(
        "/chat", json={"message": "hola"}, headers={"X-Session-Id": "no-soy-un-uuid"}
    )
    assert response.status_code == 401


# --- chat ------------------------------------------------------------------


def test_chat_answers_and_reports_its_sources(client, session_id):
    body = client.post(
        "/chat",
        json={"message": "cual es el horario de atencion"},
        headers={"X-Session-Id": session_id},
    ).json()

    assert body["route"] == "answer"
    assert body["sources"] == ["horarios.md"]
    assert body["reply"]
    assert body["conversation_id"]


def test_chat_surfaces_missing_fields(client, session_id):
    body = client.post(
        "/chat",
        json={"message": "como va mi solicitud radicada"},
        headers={"X-Session-Id": session_id},
    ).json()

    assert body["route"] == "collect"
    assert body["missing_fields"] == ["numero_radicado"]


def test_empty_message_is_rejected(client, session_id):
    response = client.post(
        "/chat", json={"message": ""}, headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 422


# --- conversations ---------------------------------------------------------


def test_history_round_trip(client, session_id):
    headers = {"X-Session-Id": session_id}
    turn = client.post(
        "/chat", json={"message": "cual es el horario"}, headers=headers
    ).json()

    listed = client.get("/conversations", headers=headers).json()
    assert len(listed) == 1

    history = client.get(
        f"/conversations/{turn['conversation_id']}/messages", headers=headers
    ).json()
    assert [m["role"] for m in history] == ["user", "agent"]


def test_cannot_read_another_users_conversation(client, session_id):
    turn = client.post(
        "/chat", json={"message": "hola"}, headers={"X-Session-Id": session_id}
    ).json()

    other = client.post("/auth/identify", json={"cedula": "9998887777"}).json()
    response = client.get(
        f"/conversations/{turn['conversation_id']}/messages",
        headers={"X-Session-Id": other["session_id"]},
    )

    assert response.status_code == 403
