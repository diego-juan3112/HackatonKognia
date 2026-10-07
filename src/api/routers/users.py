"""User registration. Thin on purpose: validate the shape, delegate, return."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import Container, get_container
from api.errors import error_responses
from models.auth import User, UserAlreadyExists
from services.auth_service import InvalidCedula

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserRequest(BaseModel):
    cedula: str = Field(min_length=1, examples=["1053812345"])
    display_name: str = Field(min_length=1, examples=["Ana"])


@router.post(
    "",
    response_model=User,
    status_code=201,
    responses=error_responses({409: "Ya existe un usuario con esa cedula. Usar POST /auth/login."}),
)
async def create_user(
    payload: CreateUserRequest,
    container: Container = Depends(get_container),
) -> User:
    """Register a person. Their name is what the agent will call them by."""
    try:
        return await container.auth.register(payload.cedula, payload.display_name)
    except InvalidCedula as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UserAlreadyExists as exc:
        raise HTTPException(
            status_code=409, detail=f"Ya existe un usuario con la cedula {exc}."
        ) from exc
