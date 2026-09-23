"""The pgvector adapter against a real database.

What the in-memory double cannot prove: that the SQL is valid, that the vector
type round-trips, that the cosine operator orders correctly, and that
re-ingesting a document replaces its chunks instead of duplicating them.
"""

from __future__ import annotations

import pytest

from models.retrieval import Document

pytestmark = pytest.mark.integration

_CORPUS = [
    Document(
        source="horarios.md",
        text=(
            "La atencion presencial es de lunes a viernes de 8:00 a 17:00. "
            "Los sabados atendemos de 9:00 a 13:00."
        ),
    ),
    Document(
        source="canales.md",
        text="Linea telefonica nacional 01 8000 123 456 disponible 24 horas.",
    ),
]


async def test_index_then_search_round_trip(retriever):
    written = await retriever.index(_CORPUS)

    assert written == await retriever.count() > 0

    results = await retriever.search("horario de atencion sabados", top_k=2)
    assert results
    assert results[0].source == "horarios.md"


async def test_vector_type_round_trips_through_postgres(retriever):
    """If pgvector registration were missing, this would fail at insert."""
    await retriever.index(_CORPUS[:1])
    results = await retriever.search("atencion presencial", top_k=1)

    assert results
    # Cosine similarity of a real match must be meaningfully above zero.
    assert 0.0 < results[0].score <= 1.0


async def test_reingesting_replaces_instead_of_duplicating(retriever):
    await retriever.index(_CORPUS)
    first = await retriever.count()

    await retriever.index(_CORPUS)

    assert await retriever.count() == first


async def test_shrinking_a_document_removes_its_stale_chunks(retriever):
    long_document = Document(source="a.md", text="palabra " * 2000)
    await retriever.index([long_document])
    many = await retriever.count()

    await retriever.index([Document(source="a.md", text="corto")])

    assert await retriever.count() < many, "los chunks viejos deben desaparecer"


async def test_search_on_empty_index_returns_empty(retriever):
    assert await retriever.count() == 0
    assert await retriever.search("lo que sea") == []


async def test_reset_truncates_everything(retriever):
    await retriever.index(_CORPUS)
    assert await retriever.count() > 0

    await retriever.reset()

    assert await retriever.count() == 0
