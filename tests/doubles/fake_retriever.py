"""RetrievalPort backed by a list in memory.

Uses the same HashingEmbedder and the same cosine scoring as the real adapter,
so ranking behaves comparably -- just without a database. What it does not
reproduce is pgvector's HNSW approximation, which is fine: with a handful of
test documents an exact scan is both faster and more predictable.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from tests.doubles.hashing_embedder import HashingEmbedder
from models.retrieval import Chunk, Document, RetrievedChunk


class InMemoryRetriever:
    """Satisfies ``models.ports.RetrievalPort`` with no I/O at all."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120) -> None:
        self._embedder = HashingEmbedder()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        self._chunks: list[tuple[Chunk, list[float]]] = []

    async def index(self, documents: Sequence[Document]) -> int:
        written = 0
        for document in documents:
            # Replace any previous version of this source, mirroring the
            # delete-then-insert the real adapter does per document.
            self._chunks = [c for c in self._chunks if c[0].source != document.source]

            pieces = [p for p in self._splitter.split_text(document.text) if p.strip()]
            vectors = self._embedder.embed_documents(pieces)
            for index, (piece, vector) in enumerate(zip(pieces, vectors)):
                self._chunks.append(
                    (
                        Chunk(
                            chunk_id=f"{document.source}:{index}",
                            source=document.source,
                            text=piece,
                            metadata=document.metadata,
                        ),
                        vector,
                    )
                )
                written += 1
        return written

    async def search(
        self,
        query: str,
        top_k: int = 4,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        if not self._chunks:
            return []

        query_vector = self._embedder.embed_query(query)

        scored: list[RetrievedChunk] = []
        for chunk, vector in self._chunks:
            if filters and not all(chunk.metadata.get(k) == v for k, v in filters.items()):
                continue
            # Both sides are L2-normalised, so the dot product is the cosine.
            similarity = sum(a * b for a, b in zip(query_vector, vector))
            scored.append(RetrievedChunk(chunk=chunk, score=similarity))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    async def count(self) -> int:
        return len(self._chunks)

    async def reset(self) -> None:
        self._chunks.clear()


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Exposed for tests that want to assert on scoring directly."""
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 0.0 if norm < 1e-12 else sum(x * y for x, y in zip(a, b)) / norm
