"""Embedding functions for the retriever.

Kept as an internal detail of the retrieval adapter rather than promoted to a
port: nobody above ``integrations/`` ever sees an embedder.

The interface is deliberately asymmetric (``embed_documents`` vs
``embed_query``). Modern retrieval models encode a question and a passage
differently, and E5 in particular requires literal ``query:`` / ``passage:``
prefixes -- forgetting them costs a noticeable chunk of retrieval quality. That
detail is handled inside the adapter so no caller has to remember it.

The hashing embedder used by the test suite lives in tests/doubles/, not here:
the product always embeds with E5.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from config import EMBEDDING_DIMENSIONS

DEFAULT_MODEL = "intfloat/multilingual-e5-base"


class Embedder(Protocol):
    """Turn texts into vectors."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _load_cache_first(model_name: str):
    """Load from the local cache without touching the network, else download.

    Without this, sentence-transformers contacts Hugging Face on *every* load
    to check for updates, even with the model already cached -- which fails or
    stalls on a bad connection. The environment variable that disables that
    (HF_HUB_OFFLINE) cannot be set from .env, because pydantic-settings does
    not export .env values to the process environment. Trying the cache first
    gets the same result with nothing to configure.
    """
    from sentence_transformers import SentenceTransformer

    try:
        return SentenceTransformer(model_name, local_files_only=True)
    except Exception:  # noqa: BLE001 - not cached yet: the one time we need the network
        return SentenceTransformer(model_name)


class E5Embedder:
    """intfloat/multilingual-e5-base, running locally on CPU. No API key.

    Chosen over the English-only models (all-MiniLM, bge-base-en, msmarco...)
    because our corpus and our users are in Spanish; an English-only model
    fails silently, returning results that are simply wrong. Measured on the
    faq_demo corpus with questions that share no words with the documents:
    3/3 correct, against 1/3 for a lexical embedder.

    Downloads ~1.1 GB the first time; afterwards loads from cache in ~10 s.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model = _load_cache_first(model_name)
        # sentence-transformers 6.x renamed this method; the fallback keeps the
        # 3.x-5.x range that requirements.txt allows.
        get_dim = getattr(self._model, "get_embedding_dimension", None) or getattr(
            self._model, "get_sentence_embedding_dimension"
        )
        actual = get_dim()
        if actual != EMBEDDING_DIMENSIONS:
            # Fail loudly here rather than letting Postgres reject every insert
            # with an opaque dimension error at ingestion time.
            raise RuntimeError(
                f"El modelo {model_name} produce vectores de {actual} dimensiones, "
                f"pero la columna document_chunks.embedding es vector({EMBEDDING_DIMENSIONS}). "
                f"Cambiar de modelo exige una migracion nueva y reindexar."
            )

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,  # cosine distance expects unit vectors
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]


def build_embedder(model: str = DEFAULT_MODEL) -> Embedder:
    """Build the product embedder."""
    return E5Embedder(model or DEFAULT_MODEL)
