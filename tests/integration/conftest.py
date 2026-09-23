"""Fixtures for the tests that genuinely need PostgreSQL.

Every test in this package is marked ``integration`` and is therefore skipped
by a plain ``pytest`` run (see pyproject.toml). Run them with:

    docker compose up -d && python -m scripts.migrate
    pytest -m integration

If the database is unreachable the whole package skips with a clear reason
rather than failing -- an absent database is not a broken test.
"""

from __future__ import annotations

import pytest

from config import get_settings
from integrations.db.conversation_repository import PostgresConversationRepository
from integrations.db.pool import create_pool
from integrations.db.user_repository import PostgresUserRepository
from integrations.retrieval.embeddings import HashingEmbedder
from integrations.retrieval.pgvector_retriever import PgVectorRetriever

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture
async def pool(settings):
    import psycopg

    pool = create_pool(settings.database_url, min_size=1, max_size=4)
    try:
        await pool.open(wait=True, timeout=5)
    except (psycopg.OperationalError, TimeoutError) as exc:
        pytest.skip(
            f"PostgreSQL no disponible en {settings.database_url_safe}: {exc}. "
            "Levanta el contenedor con `docker compose up -d` y corre "
            "`python -m scripts.migrate`."
        )

    # Every test starts from a clean slate. TRUNCATE ... CASCADE reaches
    # conversations and messages through the foreign keys.
    async with pool.connection() as conn:
        await conn.execute("TRUNCATE documents, users CASCADE")

    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def retriever(pool):
    # Hashing embeddings on purpose: these tests are about SQL and pgvector,
    # not about embedding quality, and they must not download a 1.1 GB model.
    return PgVectorRetriever(pool=pool, embedder=HashingEmbedder())


@pytest.fixture
async def users(pool):
    return PostgresUserRepository(pool)


@pytest.fixture
async def conversations(pool):
    return PostgresConversationRepository(pool)
