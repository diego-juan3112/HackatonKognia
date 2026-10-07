"""Error responses, declared so that /docs shows them.

FastAPI documents the success response and its own 422 automatically. Every
other status a router raises is invisible in Swagger unless declared, and shows
up there as "Undocumented" when it happens. Declaring them here lets whoever
builds the frontend read the whole contract instead of discovering it by trial.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Body of every error the routers raise: one human-readable sentence."""

    detail: str


def error_responses(descriptions: dict[int, str]) -> dict[int | str, dict[str, Any]]:
    """Build a route's ``responses=`` argument from status -> description."""
    return {
        code: {"model": ErrorDetail, "description": text}
        for code, text in descriptions.items()
    }


# Shared by every route that depends on current_user.
SESSION_ERRORS = {
    401: "Falta el header X-Session-Id, no es un UUID, o la sesion expiro o no existe. "
         "Solucion: POST /auth/login y usar el session_id nuevo.",
}

# Shared by every route that may call the language model.
MODEL_ERRORS = {
    502: "El modelo de lenguaje fallo. Reintentar; si persiste, revisar los logs.",
    503: "Cuota del modelo agotada o la app aun arranca. Reintentar tras el header "
         "Retry-After (segundos).",
}
