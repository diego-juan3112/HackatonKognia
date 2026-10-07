"""SQL migrations: discover, apply, and check what is pending.

Shared by three callers, which is why it lives here and not in the CLI:
- scripts/migrate.py      the command a person runs
- tests/integration       migrates the throwaway test database automatically
- api/dependencies.py     refuses to start the app on an out-of-date schema

Synchronous on purpose. It runs once, before any request, and plain psycopg
avoids the Windows event-loop issue entirely (see platform_compat.py).
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from config import REPO_ROOT

MIGRATIONS_DIR = REPO_ROOT / "migrations"

# Tracks which migrations already ran. Created before anything else so the
# runner is idempotent from a completely empty database.
_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def discover(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """Every .sql file in migrations/, in filename order."""
    if not directory.is_dir():
        raise FileNotFoundError(f"No existe el directorio de migraciones: {directory}")
    return sorted(directory.glob("*.sql"))


def database_name(conninfo: str) -> str:
    return conninfo_to_dict(conninfo).get("dbname", "")


def ensure_database(conninfo: str) -> bool:
    """Create the target database if it does not exist. Returns True if created.

    Connects to the server's maintenance database ("postgres") to do it, since
    you cannot connect to a database that does not exist yet. This is what lets
    the test database appear on its own, even on a volume created long before
    it was needed -- docker-entrypoint init scripts only run on an empty volume.
    """
    name = database_name(conninfo)
    maintenance = make_conninfo(conninfo, dbname="postgres")
    with psycopg.connect(maintenance, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if exists:
            return False
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        return True


def applied(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(_TRACKING_TABLE)
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def pending(conninfo: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Names of the migrations not yet applied to this database."""
    with psycopg.connect(conninfo) as conn:
        done = applied(conn)
        conn.commit()
    return [p.name for p in discover(directory) if p.name not in done]


def apply_pending(conninfo: str, directory: Path = MIGRATIONS_DIR, log=print) -> list[str]:
    """Apply every pending migration. Returns the names applied.

    Each migration runs in its own transaction: if one fails it rolls back
    whole, the ones before it stay applied, and the error propagates.
    """
    applied_now: list[str] = []
    with psycopg.connect(conninfo) as conn:
        done = applied(conn)
        conn.commit()
        for path in discover(directory):
            if path.name in done:
                continue
            log(f"Aplicando {path.name} ...")
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,)
                )
            applied_now.append(path.name)
    return applied_now
