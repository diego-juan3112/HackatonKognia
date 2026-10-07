"""API contract, exercised with in-memory adapters.

The app is assembled from doubles instead of the real container, so these tests
cover routing, status codes and auth enforcement without a database. The real
wiring is covered in tests/integration/.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langchain_core.exceptions import ModelRateLimitError
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver

from api.dependencies import Container
from api.main import app
from tests.doubles.fake_llm import FakeChatModel
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


def _register_and_login(client, cedula: str, name: str) -> str:
    assert client.post("/users", json={"cedula": cedula, "display_name": name}).status_code == 201
    return client.post("/auth/login", json={"cedula": cedula}).json()["session_id"]


@pytest.fixture
def session_id(client) -> str:
    return _register_and_login(client, "1053812345", "Ana")


def test_importing_the_app_needs_no_database():
    """Regression: the container must never be built at import time."""
    assert app.title.startswith("Kognia")


def test_health_reports_what_is_wired(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["llm_model"].startswith("gemini")
    assert body["embedding_model"] == "intfloat/multilingual-e5-base"
    assert body["domain"] == "faq_demo"
    assert body["indexed_chunks"] >= 1
    # The password must never appear in an operational endpoint.
    assert "***" in body["database_url"] or "@" not in body["database_url"]


# --- auth ------------------------------------------------------------------


def test_create_user_returns_201_with_the_normalised_cedula(client):
    response = client.post("/users", json={"cedula": "1.053.812.345", "display_name": "Ana"})

    assert response.status_code == 201
    assert response.json()["cedula"] == "1053812345"
    assert response.json()["display_name"] == "Ana"


def test_creating_the_same_user_twice_is_a_conflict(client):
    client.post("/users", json={"cedula": "1053812345", "display_name": "Ana"})
    again = client.post("/users", json={"cedula": "1.053.812.345", "display_name": "Ana"})
    assert again.status_code == 409


def test_create_user_requires_a_name(client):
    assert client.post("/users", json={"cedula": "1053812345"}).status_code == 422


def test_login_of_an_unregistered_cedula_is_404_and_creates_nothing(client):
    assert client.post("/auth/login", json={"cedula": "9999999999"}).status_code == 404
    # ...and it did not quietly sign them up either:
    assert client.post("/auth/login", json={"cedula": "9999999999"}).status_code == 404


def test_login_returns_a_session_for_a_registered_user(client):
    client.post("/users", json={"cedula": "1053812345", "display_name": "Ana"})
    body = client.post("/auth/login", json={"cedula": "1.053.812.345"}).json()

    assert body["cedula"] == "1053812345"
    assert body["display_name"] == "Ana"
    assert body["session_id"]


def test_malformed_cedula_is_rejected(client):
    assert client.post("/auth/login", json={"cedula": "abc"}).status_code == 422
    assert client.post("/users", json={"cedula": "abc", "display_name": "X"}).status_code == 422


def test_the_old_identify_endpoint_is_gone(client):
    assert client.post("/auth/identify", json={"cedula": "1053812345"}).status_code == 404


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

    other_session = _register_and_login(client, "9998887777", "Beto")
    response = client.get(
        f"/conversations/{turn['conversation_id']}/messages",
        headers={"X-Session-Id": other_session},
    )

    assert response.status_code == 403


# --- model failures ----------------------------------------------------------


class _RateLimitedModel(BaseChatModel):
    """Behaves like Gemini when the free-tier quota runs out."""

    @property
    def _llm_type(self) -> str:
        return "rate-limited"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise ModelRateLimitError("429 RESOURCE_EXHAUSTED")


def test_rate_limited_model_is_a_503_not_a_500(client, container, session_id):
    container.chat = ChatService(
        graph=build_graph(
            llm=_RateLimitedModel(),
            retriever=container.retriever,
            domain=container.domain,
            checkpointer=MemorySaver(),
        ),
        conversations=container.conversations,
        domain=container.domain,
    )

    response = client.post(
        "/chat", json={"message": "hola"}, headers={"X-Session-Id": session_id}
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"]
    assert "limite" in response.json()["detail"]


# --- /docs contract --------------------------------------------------------


def test_every_error_the_routes_raise_is_documented(client):
    """An undeclared status shows up in Swagger as "Undocumented"."""
    paths = client.get("/openapi.json").json()["paths"]

    def codes(path: str, method: str) -> set[str]:
        return set(paths[path][method]["responses"])

    assert {"201", "409"} <= codes("/users", "post")
    assert {"200", "404"} <= codes("/auth/login", "post")
    assert {"200", "401", "403", "404", "502", "503"} <= codes("/chat", "post")
    assert {"200", "401"} <= codes("/conversations", "get")
    assert {"200", "401", "403", "404"} <= codes("/conversations/{conversation_id}/messages", "get")


def test_the_default_chat_example_works_as_is(client, session_id):
    """Regression: Swagger used to pre-fill a made-up conversation_id -> 404."""
    body = client.get("/openapi.json").json()["paths"]["/chat"]["post"]["requestBody"]
    examples = body["content"]["application/json"]["examples"]
    default = next(iter(examples.values()))["value"]

    assert "conversation_id" not in default
    response = client.post("/chat", json=default, headers={"X-Session-Id": session_id})
    assert response.status_code == 200
