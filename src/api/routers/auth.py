"""Login. Thin on purpose: validate the shape, delegate to AuthService, return."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import Container, get_container
from api.errors import error_responses
from models.auth import Identification
from services.auth_service import InvalidCedula, UserNotFound

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    cedula: str = Field(min_length=1, examples=["1053812345"])


@router.post(
    "/login",
    response_model=Identification,
    responses=error_responses({
        404: "No hay un usuario registrado con esa cedula. Crearlo antes con POST /users.",
    }),
)
async def login(
    payload: LoginRequest,
    container: Container = Depends(get_container),
) -> Identification:
    """Open a session for a registered user.

    NOT authentication: no password is checked. Anyone who knows a registered
    cedula can obtain a session for it. Register first with POST /users.
    """
    try:
        return await container.auth.login(payload.cedula)
    except InvalidCedula as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
