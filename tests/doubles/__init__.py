"""In-memory stand-ins for every port that touches the outside world.

AGENTS.md section 5 requires each port to have one, and section 11 requires the
default suite to run with no credentials, no network and no database. These are
what make both true: `services/` gets exercised for real, PostgreSQL never
enters the picture.

They are not mocks that record calls -- they are simplified but honest
implementations, so a test that passes here is evidence the logic works, not
just evidence that a method was called.
"""

from tests.doubles.fake_repositories import (
    InMemoryConversationRepository,
    InMemoryUserRepository,
)
from tests.doubles.fake_llm import FakeChatModel
from tests.doubles.fake_retriever import InMemoryRetriever
from tests.doubles.hashing_embedder import HashingEmbedder

__all__ = [
    "InMemoryConversationRepository",
    "InMemoryRetriever",
    "InMemoryUserRepository",
]
