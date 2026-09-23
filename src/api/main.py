"""FastAPI entry point.

Nothing is built at import time: importing this module must stay free of
credentials, database connections and model downloads so that tests and CI can
import it. The container is assembled in the lifespan instead.

Run locally:
    docker compose up -d
    python -m scripts.migrate
    uvicorn api.main:app --reload --app-dir src --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.dependencies import build_container, shutdown_container
from api.routers import auth, chat, conversations


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = await build_container()
    app.state.container = container
    try:
        yield
    finally:
        await shutdown_container(container)
        app.state.container = None


app = FastAPI(
    title="Kognia Voice Agent - base generica",
    version="0.3.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(conversations.router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    """Report what is wired, so a failing demo can be diagnosed in seconds."""
    container = getattr(app.state, "container", None)
    if container is None:
        return {"status": "starting"}

    # The database check is separate from the rest: a working API with an
    # unreachable database should say so, not report a blanket "ok".
    try:
        indexed = await container.retriever.count()
        database = "ok"
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator verbatim
        indexed = None
        database = f"error: {type(exc).__name__}"

    return {
        "status": "ok" if database == "ok" else "degraded",
        "model_provider": container.settings.model_provider,
        "embedding_provider": container.settings.embedding_provider,
        "domain": container.domain.name,
        "intents": container.domain.intent_names,
        "database": database,
        "database_url": container.settings.database_url_safe,
        "indexed_chunks": indexed,
    }
