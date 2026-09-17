"""Shared fixtures.

Everything here runs offline: fake model, fake embeddings, Chroma in a tmp
directory. No fixture may require a credential or a network call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config import Settings
from integrations.llm.fake_llm import FakeChatModel
from integrations.retrieval.chroma_retriever import ChromaRetriever
from integrations.retrieval.embeddings import HashingEmbedder
from models.domain_config import DomainSpec
from models.retrieval import Document
from services.domain_loader import load_domain

REPO_ROOT = Path(__file__).resolve().parent.parent


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
def retriever(tmp_path: Path, corpus: list[Document]) -> ChromaRetriever:
    store = ChromaRetriever(
        path=tmp_path / "chroma",
        collection_name="test",
        embedder=HashingEmbedder(),
    )
    store.index(corpus)
    return store


@pytest.fixture
def empty_retriever(tmp_path: Path) -> ChromaRetriever:
    return ChromaRetriever(
        path=tmp_path / "chroma-empty",
        collection_name="test-empty",
        embedder=HashingEmbedder(),
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        model_provider="fake",
        embedding_provider="fake",
        chroma_path=tmp_path / "chroma-app",
        chroma_collection="test-app",
        domain_config_path=REPO_ROOT / "config" / "domains" / "faq_demo.yaml",
    )
