"""The connection pool every database adapter shares.

One pool per process, opened in the FastAPI lifespan and closed on shutdown.
Opening a connection per request would be slow and would exhaust Postgres under
any real load.

``register_vector_async`` teaches psycopg how to convert between Python lists
and pgvector's ``vector`` type. Without it, every embedding would have to be
serialised to a string by hand at each call site.
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool


async def _configure(conn) -> None:
    """Runs once per new connection in the pool."""
    from pgvector.psycopg import register_vector_async

    await register_vector_async(conn)


def create_pool(database_url: str, min_size: int = 1, max_size: int = 10) -> AsyncConnectionPool:
    """Build the pool without connecting yet.

    ``open=False`` keeps import and construction side-effect free; the caller
    awaits ``pool.open()`` inside the lifespan. That is what lets the test
    suite import the app with no database running.
    """
    return AsyncConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        configure=_configure,
        open=False,
    )
