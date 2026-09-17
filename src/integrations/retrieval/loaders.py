"""Document loaders, one per source format.

Adding a format on challenge day means adding one function and one entry in
``_LOADERS``. Nothing else in the pipeline changes -- that is the whole point
of AGENTS.md section 6: the RAG is designed around ingestion, not content.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from pathlib import Path

from models.retrieval import Document


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_csv(path: Path) -> str:
    """Flatten a table into "column: value" lines, one block per row."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    blocks = []
    for row in reader:
        blocks.append("\n".join(f"{k}: {v}" for k, v in row.items() if v))
    return "\n\n".join(blocks)


def _load_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


_LOADERS = {
    ".md": _load_text,
    ".markdown": _load_text,
    ".txt": _load_text,
    ".csv": _load_csv,
    ".pdf": _load_pdf,
}

SUPPORTED_SUFFIXES = tuple(_LOADERS)


def load_file(path: Path) -> Document | None:
    """Read one file. Returns None when the format is not supported."""
    loader = _LOADERS.get(path.suffix.lower())
    if loader is None:
        return None
    text = loader(path).strip()
    if not text:
        return None
    return Document(source=path.name, text=text, metadata={"path": str(path)})


def load_directory(root: str | Path) -> tuple[list[Document], list[str]]:
    """Read every supported file under ``root``, recursively.

    Returns the documents and the list of paths that were skipped, so the
    caller can report honestly instead of silently dropping files.
    """
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Ingestion path does not exist: {root}")

    paths: Iterable[Path] = [root] if root.is_file() else sorted(root.rglob("*"))

    documents: list[Document] = []
    skipped: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        document = load_file(path)
        if document is None:
            skipped.append(str(path))
        else:
            documents.append(document)

    return documents, skipped
