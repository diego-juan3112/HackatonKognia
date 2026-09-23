"""Shared fixtures.

Everything here runs offline: fake model, hashing embeddings, in-memory
retriever and repositories. No fixture may require a credential, a network
call or a running database -- AGENTS.md section 11.

Tests that genuinely need PostgreSQL live in tests/integration/ and are
skipped unless a database is reachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from config import Settings
from integrations.llm.fake_llm import FakeChatModel
from platform_compat import ensure_psycopg_compatible_event_loop
from models.domain_config import DomainSpec
from models.retrieval import Document
from services.auth_service import AuthService
from services.chat_service import ChatService
from services.domain_loader import load_domain
from services.graph.builder import build_graph
from tests.doubles import (
    InMemoryConversationRepository,
    InMemoryRetriever,
    InMemoryUserRepository,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Must run before pytest-asyncio creates any loop: on Windows the default one
# is incompatible with psycopg and the integration tests would silently skip.
ensure_psycopg_compatible_event_loop()


@pytest.fixture
def domain() -> DomainSpec:
    return load_domain(REPO_ROOT / "config" / "domains" / "faq_demo.yaml")


@pytest.fixture
def llm() -> FakeChatModel:
    return FakeChatModel()


@pytest.fixture
def corpus() -> list[Document]:
    return [
        Document(
            source="horarios.md",
            text=(
                "La atencion presencial es de lunes a viernes de 8:00 a 17:00. "
                "Los sabados atendemos de 9:00 a 13:00."
            ),
        ),
        Document(
            source="canales.md",
            text="Linea telefonica nacional 01 8000 123 456, disponible 24 horas.",
        ),
    ]


@pytest.fixture
async def retriever(corpus: list[Document]) -> InMemoryRetriever:
    store = InMemoryRetriever()
    await store.index(corpus)
    return store


@pytest.fixture
def empty_retriever() -> InMemoryRetriever:
    return InMemoryRetriever()


@pytest.fixture
def users() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def conversations() -> InMemoryConversationRepository:
    return InMemoryConversationRepository()


@pytest.fixture
def auth_service(users: InMemoryUserRepository) -> AuthService:
    return AuthService(users, session_ttl_hours=12)


@pytest.fixture
async def graph(llm, retriever, domain):
    """A compiled graph with in-memory checkpointing."""
    return build_graph(
        llm=llm,
        retriever=retriever,
        domain=domain,
        checkpointer=MemorySaver(),
    )


@pytest.fixture
async def chat_service(graph, conversations, domain) -> ChatService:
    return ChatService(graph=graph, conversations=conversations, domain=domain)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        model_provider="fake",
        embedding_provider="fake",
        domain_config_path=REPO_ROOT / "config" / "domains" / "faq_demo.yaml",
    )
