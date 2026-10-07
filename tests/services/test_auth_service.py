"""Registration and login rules, tested without a database."""

from __future__ import annotations

from uuid import uuid4

import pytest

from models.auth import UserAlreadyExists
from services.auth_service import InvalidCedula, InvalidSession, UserNotFound, normalize_cedula


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


# --- register --------------------------------------------------------------


async def test_register_creates_the_user(auth_service, users):
    user = await auth_service.register("1.053.812.345", "Ana")

    assert user.cedula == "1053812345"
    assert user.display_name == "Ana"
    assert len(users.users) == 1


async def test_registering_twice_is_rejected(auth_service):
    await auth_service.register("1053812345", "Ana")

    with pytest.raises(UserAlreadyExists):
        await auth_service.register("1053812345", "Otra Ana")


async def test_different_formats_of_the_same_cedula_are_one_user(auth_service):
    await auth_service.register("1053812345", "Ana")

    with pytest.raises(UserAlreadyExists):
        await auth_service.register("1.053.812.345", "Ana")


async def test_register_does_not_open_a_session(auth_service, users):
    """Creating an account and logging in are separate steps."""
    await auth_service.register("1053812345", "Ana")
    assert users.sessions == {}


# --- login -----------------------------------------------------------------


async def test_login_requires_a_registered_user(auth_service, users):
    with pytest.raises(UserNotFound):
        await auth_service.login("1053812345")
    assert users.users == {}, "login must never create a user"


async def test_login_opens_a_session_for_a_registered_user(auth_service, users):
    registered = await auth_service.register("1053812345", "Ana")

    result = await auth_service.login("1.053.812.345")

    assert result.user_id == registered.id
    assert result.display_name == "Ana"
    assert users.sessions[result.session_id].user_id == registered.id


async def test_each_login_opens_a_new_session(auth_service):
    await auth_service.register("1053812345", "Ana")

    first = await auth_service.login("1053812345")
    second = await auth_service.login("1053812345")

    assert first.user_id == second.user_id
    assert first.session_id != second.session_id


async def test_login_records_last_seen(auth_service, users):
    registered = await auth_service.register("1053812345", "Ana")
    assert users.users[registered.id].last_seen_at is None

    await auth_service.login("1053812345")

    assert users.users[registered.id].last_seen_at is not None


# --- sessions --------------------------------------------------------------


async def test_unknown_session_is_rejected(auth_service):
    with pytest.raises(InvalidSession):
        await auth_service.resolve_session(uuid4())


async def test_expired_session_is_rejected(auth_service, users):
    await auth_service.register("1053812345", "Ana")
    result = await auth_service.login("1053812345")
    users.expire(result.session_id)

    with pytest.raises(InvalidSession):
        await auth_service.resolve_session(result.session_id)
