"""Reto 01 voice API (docs/03 "Reto 01", docs/08 section 3). HTTP only, no database.

    uvicorn api.app_voice:app        (Vercel entrypoint: src/api/app_voice.py)

The audio never passes through here: the browser talks to the voice provider
with an ephemeral credential minted by this API (R-28). Nothing is built at
import time; the container is assembled in the lifespan.
"""

from __future__ import annotations

import base64
import binascii
import logging
import sys
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Vercel imports this file from the repo root; the code lives under src/.
_SRC = str(Path(__file__).resolve().parents[1])
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from api.voice_container import VoiceContainer, build_container  # noqa: E402
from config import get_settings  # noqa: E402
from models.analysis import UtteranceAnalysisRequest  # noqa: E402
from models.ips import TOOL_NAMES, DatasetUnavailable, Deadline, ToolRequest  # noqa: E402
from models.voice import (  # noqa: E402
    CONTRACT_VERSION,
    FeedbackEvent,
    ProviderUnavailable,
    RealtimeSessionRequest,
    SessionCreateRequest,
    SpeechSessionRequest,
)
from services.session_service import InvalidSession, SessionClaims  # noqa: E402

log = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 3_000_000  # a 30 s PCM16 clip at 24 kHz is ~1.4 MB; docs/08 section 4


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.retryable, self.headers = status, code, message, retryable, headers


def _error(status: int, code: str, message: str, retryable: bool = False,
           headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, headers=headers,
                        content={"error": {"code": code, "message": message, "retryable": retryable},
                                 "trace_id": str(uuid.uuid4())})


def create_app(build: Callable[[], VoiceContainer] | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.c = build() if build else build_container(settings)
        app.state.health_cache = None
        yield
        await app.state.c.aclose()

    app = FastAPI(title="Kognia Voice — Reto 01", version=CONTRACT_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Session-Token"], max_age=600,
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, exc.retryable, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", ()))
        return _error(422, "INVALID_INPUT", f"{where}: {first.get('msg', 'entrada inválida')}")

    @app.exception_handler(ProviderUnavailable)
    async def _provider(_: Request, exc: ProviderUnavailable) -> JSONResponse:
        return _error(503, exc.code, str(exc), retryable=True)

    @app.exception_handler(DatasetUnavailable)
    async def _dataset(_: Request, exc: DatasetUnavailable) -> JSONResponse:
        headers = {"Retry-After": str(int(exc.retry_after_s))} if exc.retry_after_s else None
        return _error(503, exc.code, "La fuente datos.gov.co no está disponible.", True, headers)

    def container(request: Request) -> VoiceContainer:
        return request.app.state.c

    def session(request: Request, c: VoiceContainer = Depends(container)) -> SessionClaims:
        try:
            claims = c.sessions.verify(request.headers.get("X-Session-Token"))
        except InvalidSession as exc:
            raise ApiError(401, "SESSION_EXPIRED", "Sesión inválida o vencida: pide una nueva con POST /sessions.") from exc
        ip = request.client.host if request.client else "?"
        for key in (f"sid:{claims.sid}", f"ip:{ip}"):
            wait = c.limiter.check(key)
            if wait is not None:
                raise ApiError(429, "RATE_LIMITED", "Demasiadas solicitudes.", True, {"Retry-After": str(int(wait))})
        return claims

    # -- routes ---------------------------------------------------------------

    @app.get("/health")
    async def health(c: VoiceContainer = Depends(container)) -> dict[str, Any]:
        cached = app.state.health_cache
        # A success is remembered 30 s; a failure only 5 s, so a cold or slow first
        # ping does not report "degraded" for half a minute.
        ttl = 30 if cached and cached[1].get("ok") else 5
        if cached is None or time.monotonic() - cached[0] > ttl:
            t0 = time.perf_counter()
            try:  # datos.gov.co is free; no paid provider is called here (docs/03)
                await c.dataset.query("SELECT count(*) AS rows", deadline=Deadline(4.5))
                source = {"ok": True, "ms": int((time.perf_counter() - t0) * 1000)}
            except DatasetUnavailable as exc:
                source = {"ok": False, "error": exc.code}
            app.state.health_cache = (time.monotonic(), source)
        source = app.state.health_cache[1]
        return {
            "status": "ok" if source.get("ok") else "degraded",
            "contract": CONTRACT_VERSION,
            "instructions_version": c.realtime.instructions_version,
            "engines": c.realtime.engines_status(),
            "voice_modes": c.realtime.voice_modes(),
            "source": source,
            **c.info,
        }

    @app.post("/sessions", status_code=201)
    async def create_session(body: SessionCreateRequest | None = None,
                             c: VoiceContainer = Depends(container)) -> dict[str, str]:
        token, expires_at = c.sessions.issue((body or SessionCreateRequest()).locale)
        return {"token": token, "expires_at": expires_at}

    @app.post("/realtime/session")
    async def realtime_session(body: RealtimeSessionRequest, _: SessionClaims = Depends(session),
                               c: VoiceContainer = Depends(container)) -> dict[str, Any]:
        return (await c.realtime.create(body)).model_dump()

    @app.post("/speech/session")
    async def speech_session(body: SpeechSessionRequest, _: SessionClaims = Depends(session),
                             c: VoiceContainer = Depends(container)) -> dict[str, Any]:
        return (await c.realtime.create_speech(body)).model_dump()

    @app.get("/dataset/brief")
    async def dataset_brief(force_live: bool = False, _: SessionClaims = Depends(session),
                            c: VoiceContainer = Depends(container)) -> dict[str, Any]:
        return await c.brief.build(bypass_cache=force_live)

    @app.post("/tools/{name}")
    async def run_tool(name: str, body: ToolRequest, _: SessionClaims = Depends(session),
                       c: VoiceContainer = Depends(container)) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            raise ApiError(404, "TOOL_UNKNOWN", f"Herramienta desconocida: {name}")
        return (await c.tools.run(name, body)).model_dump()

    @app.post("/analysis/utterance")
    async def analysis(body: UtteranceAnalysisRequest, _: SessionClaims = Depends(session),
                       c: VoiceContainer = Depends(container)) -> dict[str, Any]:
        audio = None
        if body.audio_wav_b64 and body.voice_consent:  # without consent the clip is ignored (R-26)
            try:
                audio = base64.b64decode(body.audio_wav_b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ApiError(422, "INVALID_INPUT", "audio_wav_b64 no es base64 válido") from exc
            if len(audio) > MAX_AUDIO_BYTES:
                raise ApiError(422, "INVALID_INPUT", "El recorte de audio supera 30 s")
        result = await c.analyst.analyze(body.model_copy(update={"audio_wav_b64": None}), audio)
        del audio  # the clip lives only for this request (R-26)
        return result.model_dump()

    @app.post("/feedback", status_code=202)
    async def feedback(body: FeedbackEvent, _: SessionClaims = Depends(session),
                       c: VoiceContainer = Depends(container)) -> dict[str, bool]:
        await c.feedback.record(body)
        return {"accepted": True}

    return app


app = create_app()
