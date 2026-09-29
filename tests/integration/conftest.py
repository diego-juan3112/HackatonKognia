"""Fixtures for the tests that genuinely need PostgreSQL.

These tests run against TEST_DATABASE_URL -- never DATABASE_URL. Earlier they
truncated the development database, wiping the ingested corpus and the users
every time someone ran them. Two defences now make that impossible:

1. They connect to a separate database (``kognia_test``) that is created and
   migrated automatically on first use.
2. Before truncating anything, they refuse to run unless the target database
   name ends in ``_test``. A misconfigured URL fails loudly instead of
   silently destroying data.

Every test in this package is marked ``integration`` and is skipped by a plain
``pytest`` run (see pyproject.toml). Run them with:

    docker compose up -d
    pytest -m integration
"""

from __future__ import annotations

import psycopg
import pytest

from config import get_settings, mask_password
from integrations.db.conversation_repository import PostgresConversationRepository
from integrations.db.migrations import apply_pending, database_name, ensure_database
from integrations.db.pool import create_pool
from integrations.db.user_repository import PostgresUserRepository
from integrations.retrieval.pgvector_retriever import PgVectorRetriever
from tests.doubles.hashing_embedder import HashingEmbedder

pytestmark = pytest.mark.integration


def assert_is_test_database(url: str) -> None:
    """The guard. Truncating is only ever allowed on a *_test database."""
    name = database_name(url)
    if not name.endswith("_test"):
        raise RuntimeError(
            f"Negado: los tests de integracion iban a vaciar la base '{name}'. "
            f"Solo se permite una base cuyo nombre termine en '_test'. "
            f"Revisa TEST_DATABASE_URL en tu .env."
        )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = get_settings().test_database_url
    assert_is_test_database(url)
    try:
        ensure_database(url)
        apply_pending(url, log=lambda _msg: None)
    except psycopg.OperationalError as exc:
        pytest.skip(
            f"PostgreSQL no disponible en {mask_password(url)}: {exc}. "
            "Levanta el contenedor con `docker compose up -d`."
        )
    return url


@pytest.fixture
async def pool(test_database_url):
    assert_is_test_database(test_database_url)  # again, right before destroying data
    pool = create_pool(test_database_url, min_size=1, max_size=4)
    await pool.open(wait=True, timeout=10)

    # Every test starts from a clean slate. TRUNCATE ... CASCADE reaches
    # sessions, conversations and messages through the foreign keys.
    async with pool.connection() as conn:
        await conn.execute("TRUNCATE documents, users CASCADE")

    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def retriever(pool):
    # Hashing embeddings on purpose: these tests are about SQL and pgvector,
    # not about embedding quality, and they must not load a 1.1 GB model.
    return PgVectorRetriever(pool=pool, embedder=HashingEmbedder())


@pytest.fixture
async def users(pool):
    return PostgresUserRepository(pool)


@pytest.fixture
async def conversations(pool):
    return PostgresConversationRepository(pool)
