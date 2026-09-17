"""Reindex the knowledge base.

AGENTS.md section 6: ingestion must be one repeatable command, because on
challenge day we get handed documents and need them searchable immediately.

    python -m scripts.ingest --path docs/faq_demo
    python -m scripts.ingest --path /ruta/a/lo/que/nos/den --reset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import get_settings  # noqa: E402
from integrations.retrieval.chroma_retriever import ChromaRetriever  # noqa: E402
from integrations.retrieval.embeddings import build_embedder  # noqa: E402
from integrations.retrieval.loaders import SUPPORTED_SUFFIXES, load_directory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Index documents into the knowledge base.")
    parser.add_argument("--path", required=True, help="File or directory to ingest.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop the existing index first, instead of upserting into it.",
    )
    args = parser.parse_args()

    settings = get_settings()
    retriever = ChromaRetriever(
        path=settings.chroma_path,
        collection_name=settings.chroma_collection,
        embedder=build_embedder(
            settings.embedding_provider,
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
        ),
    )

    if args.reset:
        retriever.reset()
        print("Indice reiniciado.")

    documents, skipped = load_directory(args.path)
    if not documents:
        print(f"No se encontro nada indexable en {args.path}")
        print(f"Formatos soportados: {', '.join(SUPPORTED_SUFFIXES)}")
        return 1

    chunks = retriever.index(documents)

    print(f"Documentos leidos : {len(documents)}")
    print(f"Fragmentos escritos: {chunks}")
    print(f"Total en el indice : {retriever.count()}")
    if skipped:
        print(f"Omitidos ({len(skipped)}): {', '.join(skipped[:5])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
