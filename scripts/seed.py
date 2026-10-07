"""Seed the development database: demo users and the knowledge base.

Idempotent: run it as many times as you like. Existing users are left alone
and the knowledge base is rebuilt from docs/ with the real E5 embedder.

    python -m scripts.seed

This is the data the integration tests used to wipe. They now run against
TEST_DATABASE_URL and refuse to touch any database not named *_test.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import psycopg  # noqa: E402

from config import REPO_ROOT, get_settings  # noqa: E402
from integrations.db.migrations import pending  # noqa: E402
from integrations.db.pool import create_pool  # noqa: E402
from integrations.db.user_repository import PostgresUserRepository  # noqa: E402
from platform_compat import ensure_psycopg_compatible_event_loop  # noqa: E402
from scripts.ingest import run as ingest  # noqa: E402

# Obviously fictitious cedulas: nobody should mistake these for real people.
DEMO_USERS = [
    ("1000000001", "Ana Demo"),
    ("1000000002", "Beto Demo"),
]
CORPUS = REPO_ROOT / "docs" / "faq_demo"


async def seed_users(database_url: str) -> None:
    pool = create_pool(database_url, min_size=1, max_size=2)
    await pool.open(wait=True)
    try:
        users = PostgresUserRepository(pool)
        for cedula, name in DEMO_USERS:
            if await users.find_by_cedula(cedula):
                print(f"  usuario {cedula} ({name}): ya existia")
            else:
                await users.create(cedula, name)
                print(f"  usuario {cedula} ({name}): creado")
    finally:
        await pool.close()


async def main_async() -> int:
    settings = get_settings()
    try:
        todo = await asyncio.to_thread(pending, settings.database_url)
    except psycopg.OperationalError as exc:
        print(f"No pude conectar a Postgres: {exc}\nEsta corriendo?  docker compose up -d")
        return 1
    if todo:
        print(f"Migraciones pendientes: {', '.join(todo)}. Corre primero:  python -m scripts.migrate")
        return 1

    print("Usuarios demo:")
    await seed_users(settings.database_url)

    print("\nBase de conocimiento (se reconstruye con E5):")
    return await ingest(str(CORPUS), reset=True)


def main() -> int:
    ensure_psycopg_compatible_event_loop()
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
