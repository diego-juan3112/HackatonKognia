"""Retrieval adapter: ingestion, search and the loader registry.

Runs against a real Chroma store in tmp_path with deterministic embeddings --
no network, no API key.
"""

from __future__ import annotations

from pathlib import Path

from integrations.retrieval.chroma_retriever import ChromaRetriever
from integrations.retrieval.embeddings import HashingEmbedder
from integrations.retrieval.loaders import load_directory, load_file
from models.retrieval import Document


def test_search_ranks_the_relevant_document_first(retriever):
    results = retriever.search("horario de atencion sabados", top_k=2)

    assert results
    assert results[0].source == "horarios.md"


def test_ranking_holds_on_the_real_corpus(tmp_path: Path):
    """Regression: function words used to dominate the vectors.

    With two toy documents the ranking looked fine; against the actual
    docs/faq_demo corpus the query "cual es el horario de atencion" returned
    solicitudes.md first, because "de"/"el"/"es" outweighed the content words.
    This test ingests the real corpus so that regression cannot come back.
    """
    corpus_dir = Path(__file__).resolve().parents[2] / "docs" / "faq_demo"
    documents, _ = load_directory(corpus_dir)
    store = ChromaRetriever(
        path=tmp_path / "c", collection_name="real", embedder=HashingEmbedder()
    )
    store.index(documents)

    assert store.search("cual es el horario de atencion", top_k=3)[0].source == "horarios.md"
    assert store.search("como los puedo contactar por telefono", top_k=3)[0].source == "canales.md"
    assert store.search("en que va mi radicado", top_k=3)[0].source == "solicitudes.md"


def test_search_on_empty_index_returns_empty(empty_retriever):
    assert empty_retriever.search("cualquier cosa") == []
    assert empty_retriever.count() == 0


def test_reindexing_the_same_document_does_not_duplicate(tmp_path: Path):
    store = ChromaRetriever(
        path=tmp_path / "c", collection_name="dup", embedder=HashingEmbedder()
    )
    document = Document(source="a.md", text="Texto estable para reindexar.")

    store.index([document])
    first = store.count()
    store.index([document])

    assert store.count() == first, "stable chunk ids should upsert, not append"


def test_reset_clears_the_index(retriever):
    assert retriever.count() > 0
    retriever.reset()
    assert retriever.count() == 0


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
