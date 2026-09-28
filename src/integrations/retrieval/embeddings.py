"""Embedding functions for the retriever.

Kept as an internal detail of the retrieval adapter rather than promoted to a
port: AGENTS.md section 5 lists four ports and adding a fifth for something
nobody above ``integrations/`` ever sees would be noise.

The interface is deliberately asymmetric (``embed_documents`` vs
``embed_query``). Modern retrieval models encode a question and a passage
differently, and E5 in particular requires literal ``query:`` / ``passage:``
prefixes -- forgetting them costs a noticeable chunk of retrieval quality. That
detail is handled inside the adapter so no caller has to remember it.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from config import EMBEDDING_DIMENSIONS

_TOKEN = re.compile(r"\w+", re.UNICODE)

# Without this, function words dominate every vector and retrieval ranks by
# "which document says 'de' most often". Measured effect: the query "cual es el
# horario de atencion" returned solicitudes.md ahead of horarios.md.
_STOPWORDS = frozenset(
    """
    a al algo algun alguna alguno ante antes aqui asi aun cada como con contra
    cual cuales cuando de del desde donde dos el ella ellas ello ellos en entre
    era eran es esa esas ese eso esos esta estan estas este esto estos fue
    fueron ha han hasta hay la las le les lo los mas me mi mis mucho muy no nos
    nuestra nuestro o os otra otro para pero poco por porque que quien quienes
    se sea segun ser si sin sobre son su sus tambien tanto te tiene tienen
    todo todos tu tus un una uno unos y ya yo
    """.split()
)


class Embedder(Protocol):
    """Turn texts into vectors."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _tokenize(text: str) -> list[str]:
    return [
        t
        for t in (token.lower() for token in _TOKEN.findall(text))
        if len(t) > 2 and t not in _STOPWORDS
    ]


class HashingEmbedder:
    """Deterministic, offline, dependency-free.

    Uses the hashing trick: every token maps to a dimension by a stable hash,
    counts accumulate, and the vector is L2-normalised so cosine behaves.

    Not semantic -- it only knows which words two texts share. Its job is to
    let the pipeline run in tests and offline, not to retrieve well.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        counts: dict[int, float] = {}
        for token in _tokenize(text):
            # Python's hash() is salted per process; use a stable digest.
            bucket = (
                int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:4], "little")
                % self.dimensions
            )
            counts[bucket] = counts.get(bucket, 0.0) + 1.0

        vector = [0.0] * self.dimensions
        for bucket, count in counts.items():
            # Sublinear term frequency: a word repeated ten times is not ten
            # times more informative than one seen once.
            vector[bucket] = 1.0 + math.log(count)

        norm = math.sqrt(sum(v * v for v in vector))
        if norm < 1e-12:
            # An empty or all-stopword text: return a valid unit vector so the
            # database never receives a zero vector.
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    # Symmetric: there is no query/passage distinction to make here.
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class E5Embedder:
    """intfloat/multilingual-e5-base, running locally on CPU.

    Chosen over the English-only models (all-MiniLM, bge-base-en, msmarco...)
    because our corpus and our users are in Spanish; an English-only model
    fails silently, returning results that are simply wrong.

    Downloads ~1.1 GB from Hugging Face the first time and caches it. That
    first run needs network; every run after works offline.
    """

    def __init__(self, model_name: str = "intfloat/multilingual-e5-base") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        # sentence-transformers 6.x renamed this method; the old name still
        # works but warns and will be removed. The fallback keeps the 3.x-5.x
        # range that requirements.txt allows.
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


def build_embedder(provider: str, model: str = "") -> Embedder:
    """Select the embedder declared in settings."""
    if provider == "fake":
        return HashingEmbedder()
    if provider == "local":
        return E5Embedder(model or "intfloat/multilingual-e5-base")
    raise ValueError(f"EMBEDDING_PROVIDER desconocido: {provider!r}")
