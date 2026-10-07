"""Loaders, embeddings and the in-memory retriever.

The real pgvector adapter is exercised in tests/integration/, which needs a
database. What is covered here is everything that does not: document parsing,
embedding behaviour, and ranking.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config import EMBEDDING_DIMENSIONS
from tests.doubles.hashing_embedder import HashingEmbedder
from integrations.retrieval.loaders import load_directory, load_file
from models.retrieval import Document
from tests.doubles import InMemoryRetriever


async def test_search_ranks_the_relevant_document_first(retriever):
    results = await retriever.search("horario de atencion sabados", top_k=2)

    assert results
    assert results[0].source == "horarios.md"


async def test_ranking_holds_on_the_real_corpus(tmp_path: Path):
    """Regression: function words used to dominate the vectors.

    With two toy documents the ranking looked fine; against the actual
    docs/faq_demo corpus the query "cual es el horario de atencion" returned
    solicitudes.md first, because "de"/"el"/"es" outweighed the content words.
    """
    corpus_dir = Path(__file__).resolve().parents[2] / "docs" / "faq_demo"
    documents, _ = load_directory(corpus_dir)
    store = InMemoryRetriever()
    await store.index(documents)

    top = await store.search("cual es el horario de atencion", top_k=3)
    assert top[0].source == "horarios.md"

    top = await store.search("en que va mi radicado", top_k=3)
    assert top[0].source == "solicitudes.md"


async def test_search_on_empty_index_returns_empty(empty_retriever):
    assert await empty_retriever.search("cualquier cosa") == []
    assert await empty_retriever.count() == 0


async def test_reindexing_the_same_document_does_not_duplicate():
    store = InMemoryRetriever()
    document = Document(source="a.md", text="Texto estable para reindexar.")

    await store.index([document])
    first = await store.count()
    await store.index([document])

    assert await store.count() == first, "reindexar debe reemplazar, no acumular"


async def test_reset_clears_the_index(retriever):
    assert await retriever.count() > 0
    await retriever.reset()
    assert await retriever.count() == 0


# --- embeddings ------------------------------------------------------------


def test_hashing_embedder_matches_the_column_width():
    """A mismatch here would make every pgvector insert fail at ingestion."""
    vector = HashingEmbedder().embed_query("cualquier texto")
    assert len(vector) == EMBEDDING_DIMENSIONS


def test_hashing_embedder_is_deterministic_across_calls():
    """Python's hash() is salted per process; this must not depend on it."""
    a = HashingEmbedder().embed_query("horario de atencion")
    b = HashingEmbedder().embed_query("horario de atencion")
    assert a == b


def test_empty_text_still_produces_a_unit_vector():
    """A zero vector would be rejected by pgvector's cosine operator."""
    vector = HashingEmbedder().embed_query("de el la y")  # solo stopwords
    assert abs(sum(v * v for v in vector) - 1.0) < 1e-9


# --- loaders ---------------------------------------------------------------


def test_loaders_cover_the_declared_formats(tmp_path: Path):
    (tmp_path / "a.md").write_text("# Titulo\nContenido", encoding="utf-8")
    (tmp_path / "b.txt").write_text("texto plano", encoding="utf-8")
    (tmp_path / "c.csv").write_text("col1,col2\nv1,v2\n", encoding="utf-8")
    (tmp_path / "d.xyz").write_text("formato no soportado", encoding="utf-8")

    documents, skipped = load_directory(tmp_path)

    assert {d.source for d in documents} == {"a.md", "b.txt", "c.csv"}
    assert len(skipped) == 1
    csv_doc = next(d for d in documents if d.source == "c.csv")
    assert "col1: v1" in csv_doc.text


def test_unsupported_format_returns_none(tmp_path: Path):
    path = tmp_path / "x.docx"
    path.write_text("irrelevante", encoding="utf-8")

    assert load_file(path) is None


def test_missing_path_fails_loudly():
    with pytest.raises(FileNotFoundError):
        load_directory("/ruta/que/no/existe")
