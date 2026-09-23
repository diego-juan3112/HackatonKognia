"""Reindex the knowledge base into PostgreSQL + pgvector.

AGENTS.md section 6: ingestion must be one repeatable command, because on
challenge day we get handed documents and need them searchable immediately.

    python -m scripts.ingest --path docs/faq_demo
    python -m scripts.ingest --path /ruta/a/lo/que/nos/den --reset
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import psycopg  # noqa: E402

from config import get_settings  # noqa: E402
from integrations.db.pool import create_pool  # noqa: E402
from integrations.retrieval.embeddings import build_embedder  # noqa: E402
from integrations.retrieval.loaders import SUPPORTED_SUFFIXES, load_directory  # noqa: E402
from integrations.retrieval.pgvector_retriever import PgVectorRetriever  # noqa: E402
from platform_compat import ensure_psycopg_compatible_event_loop  # noqa: E402


async def run(path: str, reset: bool) -> int:
    settings = get_settings()

    documents, skipped = load_directory(path)
    if not documents:
        print(f"No se encontro nada indexable en {path}")
        print(f"Formatos soportados: {', '.join(SUPPORTED_SUFFIXES)}")
        return 1

    # Built before opening the pool: with EMBEDDING_PROVIDER=local this loads a
    # ~1.1 GB model, and failing there should not leave a connection dangling.
    if settings.embedding_provider == "local":
        print(f"Embeddings: local ({settings.embedding_model})")
    else:
        # Naming a model here would be misleading: the hashing embedder ignores
        # EMBEDDING_MODEL entirely.
        print("Embeddings: fake (lexico, sin modelo -- no es semantico)")
    embedder = build_embedder(settings.embedding_provider, settings.embedding_model)

    pool = create_pool(settings.database_url, min_size=1, max_size=4)
    try:
        await pool.open(wait=True)
    except psycopg.OperationalError as exc:
        print("No pude conectar a Postgres.")
        print(f"  URL: {settings.database_url_safe}")
        print(f"  Error: {exc}")
        print("\nEsta corriendo el contenedor?  docker compose up -d")
        return 1

    try:
        retriever = PgVectorRetriever(pool=pool, embedder=embedder)

        if reset:
            await retriever.reset()
            print("Indice reiniciado.")

        chunks = await retriever.index(documents)

        print(f"Documentos leidos  : {len(documents)}")
        print(f"Fragmentos escritos: {chunks}")
        print(f"Total en el indice : {await retriever.count()}")
        if skipped:
            print(f"Omitidos ({len(skipped)}): {', '.join(skipped[:5])}")
    finally:
        await pool.close()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Index documents into the knowledge base.")
    parser.add_argument("--path", required=True, help="File or directory to ingest.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop the existing index first, instead of upserting into it.",
    )
    args = parser.parse_args()
    ensure_psycopg_compatible_event_loop()
    return asyncio.run(run(args.path, args.reset))


if __name__ == "__main__":
    raise SystemExit(main())
