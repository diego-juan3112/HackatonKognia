"""RetrievalPort implemented over Chroma.

Chroma was chosen over FAISS because persistence, upsert and metadata
filtering come for free; FAISS would mean hand-rolling index serialisation and
the id-to-document map. On challenge day we want reindexing to be one command.

Embeddings are passed in explicitly rather than letting Chroma pick its default
function -- the default downloads an ONNX model on first use, which would break
the "runs with no network" requirement of AGENTS.md section 11.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from integrations.retrieval.embeddings import Embedder
from models.retrieval import Chunk, Document, RetrievedChunk


def _chunk_id(source: str, index: int, text: str) -> str:
    """Stable id, so re-ingesting the same file replaces instead of duplicating."""
    digest = hashlib.sha1(f"{source}:{index}:{text}".encode("utf-8")).hexdigest()[:16]
    return f"{source}:{index}:{digest}"


class ChromaRetriever:
    """Concrete adapter satisfying ``models.ports.RetrievalPort``."""

    def __init__(
        self,
        path: str | Path,
        collection_name: str,
        embedder: Embedder,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._embedder = embedder
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            # Vectors are L2-normalised, so cosine is the right space.
            metadata={"hnsw:space": "cosine"},
        )

    # -- RetrievalPort ----------------------------------------------------
    def index(self, documents: Sequence[Document]) -> int:
        chunks: list[Chunk] = []
        for document in documents:
            for i, piece in enumerate(self._splitter.split_text(document.text)):
                chunks.append(
                    Chunk(
                        chunk_id=_chunk_id(document.source, i, piece),
                        source=document.source,
                        text=piece,
                        metadata=document.metadata,
                    )
                )

        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=texts,
            embeddings=self._embedder.embed(texts),
            metadatas=[{"source": c.source, **c.metadata} for c in chunks],
        )
        return len(chunks)

    def search(
        self,
        query: str,
        top_k: int = 4,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []

        result = self._collection.query(
            query_embeddings=self._embedder.embed([query]),
            n_results=min(top_k, self.count()),
            where=dict(filters) if filters else None,
        )

        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        out: list[RetrievedChunk] = []
        for chunk_id, text, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            metadata = dict(metadata or {})
            source = str(metadata.pop("source", "unknown"))
            out.append(
                RetrievedChunk(
                    chunk=Chunk(
                        chunk_id=str(chunk_id),
                        source=source,
                        text=str(text),
                        metadata={k: str(v) for k, v in metadata.items()},
                    ),
                    # Cosine distance in [0, 2] -> similarity in [-1, 1].
                    score=1.0 - float(distance),
                )
            )
        return out

    def count(self) -> int:
        return int(self._collection.count())

    def reset(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
