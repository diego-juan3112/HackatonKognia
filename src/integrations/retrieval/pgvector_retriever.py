"""RetrievalPort implemented over PostgreSQL + pgvector.

Replaces the previous Chroma adapter. The motivation was not that Chroma was
bad at vectors -- it was that an agentic chat needs users, conversations and
history alongside the vectors, and keeping those in two stores means keeping
two stores in sync. One database removes that problem entirely.

Asynchronous because FastAPI and the connection pool are: a blocking query here
would stall the whole event loop.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from integrations.retrieval.embeddings import Embedder
from models.retrieval import Chunk, Document, RetrievedChunk


class PgVectorRetriever:
    """Concrete adapter satisfying ``models.ports.RetrievalPort``."""

    def __init__(
        self,
        pool: AsyncConnectionPool,
        embedder: Embedder,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    # -- RetrievalPort ----------------------------------------------------
    async def index(self, documents: Sequence[Document]) -> int:
        """Insert or replace documents. Returns the number of chunks written."""
        written = 0

        for document in documents:
            pieces = [p for p in self._splitter.split_text(document.text) if p.strip()]
            if not pieces:
                continue

            vectors = self._embedder.embed_documents(pieces)

            async with self._pool.connection() as conn:
                # One transaction per document: re-ingesting a file replaces
                # its chunks atomically, never leaving it half-indexed.
                async with conn.transaction():
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute(
                            "INSERT INTO documents (source, title, metadata) "
                            "VALUES (%s, %s, %s) "
                            "ON CONFLICT (source) DO UPDATE "
                            "  SET title = EXCLUDED.title, "
                            "      metadata = EXCLUDED.metadata, "
                            "      indexed_at = now() "
                            "RETURNING id",
                            # Jsonb(...) is required: psycopg3 will not adapt a
                            # bare dict to a jsonb placeholder.
                            (document.source, document.source, Jsonb(document.metadata)),
                        )
                        document_id = (await cur.fetchone())["id"]

                        # Chunk count can shrink between ingestions; deleting
                        # first avoids leaving stale trailing chunks behind.
                        await cur.execute(
                            "DELETE FROM document_chunks WHERE document_id = %s",
                            (document_id,),
                        )

                        for index, (piece, vector) in enumerate(zip(pieces, vectors)):
                            await cur.execute(
                                "INSERT INTO document_chunks "
                                "(document_id, chunk_index, content, embedding, metadata) "
                                "VALUES (%s, %s, %s, %s, %s)",
                                (
                                    document_id,
                                    index,
                                    piece,
                                    vector,
                                    Jsonb(document.metadata),
                                ),
                            )
                        written += len(pieces)

        return written

    async def search(
        self,
        query: str,
        top_k: int = 4,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        vector = self._embedder.embed_query(query)

        # <=> is pgvector's cosine distance operator and is what the HNSW index
        # is built for; any other expression here would silently skip the index.
        #
        # The ::vector cast is not optional. On INSERT, Postgres infers the type
        # from the target column, but an operator has no column to infer from,
        # and the parameter arrives untyped:
        #   operator does not exist: vector <=> unknown
        sql = """
            SELECT c.id, c.chunk_index, c.content, c.metadata,
                   d.source, c.embedding <=> %s::vector AS distance
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
        """
        params: list[Any] = [vector]

        if filters:
            sql += " WHERE c.metadata @> %s"
            params.append(Jsonb(dict(filters)))

        sql += " ORDER BY distance LIMIT %s"
        params.append(top_k)

        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()

        return [
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id=str(row["id"]),
                    source=row["source"],
                    text=row["content"],
                    metadata={k: str(v) for k, v in (row["metadata"] or {}).items()},
                ),
                # Cosine distance in [0, 2] -> similarity in [-1, 1].
                score=1.0 - float(row["distance"]),
            )
            for row in rows
        ]

    async def count(self) -> int:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM document_chunks")
                return int((await cur.fetchone())[0])

    async def reset(self) -> None:
        """Drop everything indexed. Chunks go with the documents by cascade."""
        async with self._pool.connection() as conn:
            await conn.execute("TRUNCATE documents CASCADE")
