"""UserRepositoryPort over PostgreSQL.

All SQL touching identity lives here. ``services/auth_service.py`` calls this
through the Protocol and never sees psycopg.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from models.auth import Session, User, UserAlreadyExists


class PostgresUserRepository:
    """Concrete adapter satisfying ``models.ports.UserRepositoryPort``."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def find_by_cedula(self, cedula: str) -> User | None:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, cedula, display_name, created_at, last_seen_at "
                    "FROM users WHERE cedula = %s",
                    (cedula,),
                )
                row = await cur.fetchone()
        return User(**row) if row else None

    async def find_by_id(self, user_id: UUID) -> User | None:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, cedula, display_name, created_at, last_seen_at "
                    "FROM users WHERE id = %s",
                    (user_id,),
                )
                row = await cur.fetchone()
        return User(**row) if row else None

    async def create(self, cedula: str, display_name: str | None = None) -> User:
        try:
            async with self._pool.connection() as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "INSERT INTO users (cedula, display_name) VALUES (%s, %s) "
                        "RETURNING id, cedula, display_name, created_at, last_seen_at",
                        (cedula, display_name),
                    )
                    row = await cur.fetchone()
        except UniqueViolation as exc:
            # The UNIQUE constraint is the real guard against duplicates: a
            # check-then-insert in the service can still race. Translate it so
            # nothing above integrations/ has to know about psycopg.
            raise UserAlreadyExists(cedula) from exc
        return User(**row)

    async def touch_last_seen(self, user_id: UUID) -> None:
        async with self._pool.connection() as conn:
            await conn.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (user_id,))

    async def create_session(self, user_id: UUID, ttl_hours: int) -> Session:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "INSERT INTO sessions (user_id, expires_at) VALUES (%s, %s) "
                    "RETURNING id, user_id, created_at, expires_at, revoked_at",
                    (user_id, expires_at),
                )
                row = await cur.fetchone()
        return Session(**row)

    async def get_session(self, session_id: UUID) -> Session | None:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, user_id, created_at, expires_at, revoked_at "
                    "FROM sessions WHERE id = %s",
                    (session_id,),
                )
                row = await cur.fetchone()
        return Session(**row) if row else None
