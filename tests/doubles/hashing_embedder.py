"""Test double for the embedder: hashing bag-of-words vectors.

Lives in tests/ on purpose. The product always embeds with E5; this exists so
the suite can build and search an index with no model download and no network.

Not semantic -- it only knows which words two texts share. That is enough to
test that retrieval is wired correctly, and deliberately not enough to pass for
real retrieval quality.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

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
