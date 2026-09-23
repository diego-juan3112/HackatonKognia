"""Apply pending SQL migrations.

Deliberately tiny: no ORM, no Alembic. The schema is six tables and the point
is that anyone on the team can read `migrations/*.sql` and know exactly what
the database looks like, with no framework in between.

    python -m scripts.migrate           # apply what is pending
    python -m scripts.migrate --status  # show what ran and what is pending
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import psycopg  # noqa: E402

from config import REPO_ROOT, get_settings  # noqa: E402

MIGRATIONS_DIR = REPO_ROOT / "migrations"

# Tracks which migrations already ran. Created before anything else so the
# runner is idempotent from a completely empty database.
_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def discover() -> list[Path]:
    """Every .sql file in migrations/, in filename order."""
    if not MIGRATIONS_DIR.is_dir():
        raise FileNotFoundError(f"No existe el directorio de migraciones: {MIGRATIONS_DIR}")
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def applied_versions(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(_TRACKING_TABLE)
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations.")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Only report what is applied and what is pending.",
    )
    args = parser.parse_args()

    settings = get_settings()
    migrations = discover()

    try:
        conn = psycopg.connect(settings.database_url, autocommit=False)
    except psycopg.OperationalError as exc:
        print("No pude conectar a Postgres.")
        print(f"  URL: {settings.database_url_safe}")
        print(f"  Error: {exc}")
        print("\nEsta corriendo el contenedor?  docker compose up -d")
        return 1

    with conn:
        done = applied_versions(conn)
        conn.commit()

        if args.status:
            for path in migrations:
                mark = "aplicada" if path.name in done else "PENDIENTE"
                print(f"  [{mark}] {path.name}")
            return 0

        pending = [p for p in migrations if p.name not in done]
        if not pending:
            print(f"Nada que aplicar. {len(done)} migracion(es) ya estaban al dia.")
            return 0

        for path in pending:
            print(f"Aplicando {path.name} ...", end=" ", flush=True)
            try:
                # Each migration runs in its own transaction: if one fails it
                # rolls back whole, and the ones before it stay applied.
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (path.name,),
                    )
            except psycopg.Error as exc:
                print("FALLO")
                print(f"  {exc}")
                return 1
            print("ok")

        print(f"\n{len(pending)} migracion(es) aplicada(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
