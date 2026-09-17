"""FastAPI entry point.

Nothing is built at import time: importing this module must stay free of
credentials, network and disk work so that tests and CI can import it. The
container is assembled in the lifespan instead.

Run locally:
    uvicorn api.main:app --reload --app-dir src --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.dependencies import build_container
from api.routers import chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.container = build_container()
    yield
    app.state.container = None


app = FastAPI(
    title="Kognia Voice Agent - base generica",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(chat.router)


@app.get("/health")
def health() -> dict:
    """Report what is wired, so a failing demo can be diagnosed in seconds."""
    container = getattr(app.state, "container", None)
    if container is None:
        return {"status": "starting"}

    return {
        "status": "ok",
        "model_provider": container.settings.model_provider,
        "embedding_provider": container.settings.embedding_provider,
        "domain": container.domain.name,
        "intents": container.domain.intent_names,
        "indexed_chunks": container.retriever.count(),
    }
