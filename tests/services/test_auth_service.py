"""Identification rules, tested without a database."""

from __future__ import annotations

from uuid import uuid4

import pytest

from services.auth_service import InvalidCedula, InvalidSession, normalize_cedula


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1053812345", "1053812345"),
        ("1.053.812.345", "1053812345"),
        ("1 053 812 345", "1053812345"),
        ("10-538-123", "10538123"),
    ],
)
def test_cedula_is_normalised_to_one_canonical_form(raw, expected):
    """Otherwise the same person becomes two rows."""
    assert normalize_cedula(raw) == expected


@pytest.mark.parametrize("raw", ["", "12345", "abc123456", "12345678901", None])
def test_invalid_cedulas_are_rejected(raw):
    with pytest.raises(InvalidCedula):
        normalize_cedula(raw)


async def test_first_identification_creates_the_user(auth_service, users):
    result = await auth_service.identify("1.053.812.345")

    assert result.cedula == "1053812345"
    assert len(users.users) == 1
    assert users.sessions[result.session_id].user_id == result.user_id


async def test_second_identification_reuses_the_same_user(auth_service, users):
    first = await auth_service.identify("1053812345")
    second = await auth_service.identify("1053812345")

    assert first.user_id == second.user_id
    assert len(users.users) == 1, "no debe duplicar el usuario"
    assert first.session_id != second.session_id, "cada identificacion abre sesion nueva"


async def test_different_formats_of_the_same_cedula_are_one_user(auth_service, users):
    await auth_service.identify("1053812345")
    await auth_service.identify("1.053.812.345")

    assert len(users.users) == 1


async def test_unknown_session_is_rejected(auth_service):
    with pytest.raises(InvalidSession):
        await auth_service.resolve_session(uuid4())


async def test_expired_session_is_rejected(auth_service, users):
    result = await auth_service.identify("1053812345")
    users.expire(result.session_id)

    with pytest.raises(InvalidSession):
        await auth_service.resolve_session(result.session_id)
