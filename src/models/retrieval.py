"""Data shapes for the knowledge base (RAG).

These types are what crosses the boundary out of ``integrations/retrieval``.
No Chroma type, no embedding vector and no loader detail ever reaches
``services/`` -- only the structures declared here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A source document before it is split into chunks."""

    source: str = Field(description="Origin of the document, usually a file path.")
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class Chunk(BaseModel):
    """A slice of a document, sized for embedding and retrieval."""

    chunk_id: str
    source: str
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    """A chunk returned by a search, with its relevance score."""

    chunk: Chunk
    score: float = Field(description="Higher means more relevant.")

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def source(self) -> str:
        return self.chunk.source


class IngestionReport(BaseModel):
    """Result of an indexing run, so the caller can verify what happened."""

    documents_read: int = 0
    chunks_indexed: int = 0
    skipped: list[str] = Field(default_factory=list)
