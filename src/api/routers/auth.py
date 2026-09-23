"""Identification endpoint.

Thin on purpose: validate the shape, delegate to AuthService, return.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import Container, get_container
from models.auth import Identification
from services.auth_service import InvalidCedula

router = APIRouter(prefix="/auth", tags=["auth"])


class IdentifyRequest(BaseModel):
    cedula: str = Field(min_length=1, examples=["1053812345"])
    display_name: str | None = None


@router.post("/identify", response_model=Identification)
async def identify(
    payload: IdentifyRequest,
    container: Container = Depends(get_container),
) -> Identification:
    """Find or create the user behind a cedula and open a session.

    NOT authentication: no password is checked. Anyone who knows a cedula can
    obtain a session for it.
    """
    try:
        return await container.auth.identify(payload.cedula, payload.display_name)
    except InvalidCedula as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
