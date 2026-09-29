"""Apply pending SQL migrations.

Deliberately tiny: no ORM, no Alembic. The schema is a handful of tables and
the point is that anyone can read `migrations/*.sql` and know exactly what the
database looks like. The logic lives in src/integrations/db/migrations.py so
the tests and the app startup check reuse it.

    python -m scripts.migrate           # development database (DATABASE_URL)
    python -m scripts.migrate --status  # what ran and what is pending
    python -m scripts.migrate --test    # test database (TEST_DATABASE_URL)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import psycopg  # noqa: E402

from config import get_settings, mask_password  # noqa: E402
from integrations.db.migrations import (  # noqa: E402
    apply_pending,
    database_name,
    discover,
    ensure_database,
    pending,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations.")
    parser.add_argument("--status", action="store_true", help="Only report, apply nothing.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Target TEST_DATABASE_URL instead of DATABASE_URL (creates it if missing).",
    )
    args = parser.parse_args()

    settings = get_settings()
    url = settings.test_database_url if args.test else settings.database_url
    print(f"Base: {database_name(url)}  ({mask_password(url)})")

    try:
        if args.test and ensure_database(url):
            print("Base de pruebas creada.")
        todo = pending(url)
    except psycopg.OperationalError as exc:
        print("No pude conectar a Postgres.")
        print(f"  Error: {exc}")
        print("\nEsta corriendo el contenedor?  docker compose up -d")
        return 1

    if args.status:
        for path in discover():
            mark = "PENDIENTE" if path.name in todo else "aplicada"
            print(f"  [{mark}] {path.name}")
        return 0

    if not todo:
        print("Nada que aplicar: el esquema esta al dia.")
        return 0

    try:
        done = apply_pending(url)
    except psycopg.Error as exc:
        print(f"FALLO: {exc}")
        return 1
    print(f"{len(done)} migracion(es) aplicada(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
