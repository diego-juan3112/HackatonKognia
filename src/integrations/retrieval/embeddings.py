"""Embedding functions for the retriever.

Kept as an internal detail of the retrieval adapter rather than promoted to a
port: AGENTS.md section 5 lists four ports and adding a fifth for something
nobody above ``integrations/`` ever sees would be noise.

The fake embedder is not a stub that returns zeros. It is a hashing bag-of-
words vectoriser, so documents that share vocabulary really do land near each
other. That gives usable lexical retrieval with no network and no API key,
which is what lets the full pipeline run offline.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

_TOKEN = re.compile(r"\w+", re.UNICODE)
FAKE_DIMENSIONS = 256

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

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _tokenize(text: str) -> list[str]:
    return [
        t
        for t in (token.lower() for token in _TOKEN.findall(text))
        if len(t) > 2 and t not in _STOPWORDS
    ]


class HashingEmbedder:
    """Deterministic, offline, dependency-free.

    Uses the hashing trick: every token is mapped to a dimension by a stable
    hash, counts are accumulated and the vector is L2-normalised so cosine
    similarity behaves.
    """

    def __init__(self, dimensions: int = FAKE_DIMENSIONS) -> None:
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
            # An empty or all-stopword text: return a valid unit vector so
            # Chroma never receives a zero vector.
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class OpenAIEmbedder:
    """Real embeddings. Requires a key and network; never used by the suite."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        if not api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=openai pero falta OPENAI_API_KEY en tu .env"
            )
        from langchain_openai import OpenAIEmbeddings

        self._client = OpenAIEmbeddings(model=model, api_key=api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self._client.embed_documents(list(texts))


def build_embedder(provider: str, api_key: str = "", model: str = "") -> Embedder:
    """Select the embedder declared in settings."""
    if provider == "fake":
        return HashingEmbedder()
    if provider == "openai":
        return OpenAIEmbedder(api_key=api_key, model=model or "text-embedding-3-small")
    raise ValueError(f"EMBEDDING_PROVIDER desconocido: {provider!r}")
