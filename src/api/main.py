"""FastAPI entry point.

Nothing is built at import time: importing this module must stay free of
credentials, database connections and model downloads so that tests and CI can
import it. The container is assembled in the lifespan instead.

Run locally:
    docker compose up -d
    python -m scripts.migrate
    python -m scripts.seed
    python -m scripts.serve      # not uvicorn directly: see docs/01-arquitectura.md 4.4
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain_core.exceptions import ModelError, ModelRateLimitError

from api.dependencies import build_container, shutdown_container
from api.routers import auth, chat, conversations, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = await build_container()
    app.state.container = container
    try:
        yield
    finally:
        await shutdown_container(container)
        app.state.container = None


# Rendered at the top of /docs: the order of calls is the one thing Swagger
# cannot infer from the routes themselves.
_DESCRIPTION = """
Flujo minimo para conversar con el agente:

1. **`POST /users`** crea a la persona (una sola vez). El seed ya trae a
   `1000000001` (Ana Demo) y `1000000002` (Beto Demo).
2. **`POST /auth/login`** con su cedula devuelve un `session_id`.
3. **`POST /chat`** con el header **`X-Session-Id: <session_id>`**. En el primer
   turno **no** envies `conversation_id`; en los siguientes, envia el que
   devolvio el primer turno.

Todas las rutas salvo `/users`, `/auth/login` y `/health` exigen `X-Session-Id`.
Los errores traen siempre `{"detail": "<explicacion>"}`.

**Aviso:** identificar por cedula no es autenticar; no hay contrasena.
"""

app = FastAPI(
    title="Kognia Voice Agent - base generica",
    version="0.4.1",
    description=_DESCRIPTION,
    lifespan=lifespan,
)

app.include_router(users.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(conversations.router)


# Model failures, mapped to honest status codes. These exception types come
# from langchain-core, not from Google: the API stays unaware of which provider
# is behind LLMPort, and a provider swap would not touch this.


@app.exception_handler(ModelRateLimitError)
async def _rate_limited(_request: Request, exc: ModelRateLimitError) -> JSONResponse:
    # The free Gemini tier caps requests per minute and a RAG turn costs two
    # calls. Say so, instead of a 500 that looks like a bug.
    return JSONResponse(
        status_code=503,
        content={"detail": "El modelo de lenguaje alcanzo su limite de peticiones. "
                           "Reintenta en unos segundos."},
        headers={"Retry-After": "10"},
    )


@app.exception_handler(ModelError)
async def _model_failed(_request: Request, exc: ModelError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": f"El modelo de lenguaje fallo ({type(exc).__name__})."},
    )


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
        "llm_model": container.settings.gemini_model,
        "embedding_model": container.settings.embedding_model,
        "domain": container.domain.name,
        "intents": container.domain.intent_names,
        "database": database,
        "database_url": container.settings.database_url_safe,
        "indexed_chunks": indexed,
    }
