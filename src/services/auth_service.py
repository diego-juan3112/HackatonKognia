"""Identification by cedula.

SECURITY NOTE, stated plainly because it matters: this is identification, not
authentication. There is no password and no proof of ownership -- anyone who
knows a cedula can act as that person. It is a deliberate scope decision for
the demo. Do not expose anything sensitive through endpoints guarded only by
this until a real credential check exists.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from models.auth import Identification, Session, User, UserAlreadyExists
from models.ports import UserRepositoryPort

# Colombian cedulas are 6-10 digits. Kept deliberately loose: rejecting a valid
# citizen's document during a demo is worse than accepting an odd one.
_CEDULA = re.compile(r"^\d{6,10}$")


class InvalidCedula(ValueError):
    """The cedula is not in an acceptable format."""


class InvalidSession(PermissionError):
    """The session is unknown, expired or revoked."""


def normalize_cedula(raw: str) -> str:
    """Strip dots, spaces and dashes, then validate.

    People type "1.053.812.345" or "1 053 812 345"; the database should hold
    one canonical form so the same person is never two rows.
    """
    cleaned = re.sub(r"[.\s-]", "", raw or "")
    if not _CEDULA.match(cleaned):
        raise InvalidCedula(
            f"'{raw}' no parece una cedula valida (se esperan entre 6 y 10 digitos)."
        )
    return cleaned


class UserNotFound(LookupError):
    """No user is registered with that cedula."""


class AuthService:
    """Register users and open sessions for registered ones.

    Registration and login are separate on purpose: logging in with an unknown
    cedula is an error, not a silent sign-up.
    """

    def __init__(self, users: UserRepositoryPort, session_ttl_hours: int = 12) -> None:
        self._users = users
        self._ttl = session_ttl_hours

    async def register(self, cedula: str, display_name: str) -> User:
        """Create a user. Raises UserAlreadyExists if the cedula is taken."""
        cedula = normalize_cedula(cedula)
        if await self._users.find_by_cedula(cedula) is not None:
            raise UserAlreadyExists(cedula)
        # The repository also raises UserAlreadyExists if a concurrent request
        # won the race between the check above and this insert.
        return await self._users.create(cedula, display_name.strip() or None)

    async def login(self, cedula: str) -> Identification:
        """Open a session for a registered user. Raises UserNotFound otherwise."""
        cedula = normalize_cedula(cedula)
        user = await self._users.find_by_cedula(cedula)
        if user is None:
            raise UserNotFound(f"No hay un usuario registrado con la cedula {cedula}.")

        await self._users.touch_last_seen(user.id)
        session = await self._users.create_session(user.id, self._ttl)

        return Identification(
            user_id=user.id,
            session_id=session.id,
            cedula=user.cedula,
            display_name=user.display_name,
            expires_at=session.expires_at,
        )

    async def resolve_session(self, session_id: UUID) -> Session:
        """Return the session if it is usable, otherwise raise.

        Expiry and revocation are checked here rather than in SQL so the rule
        lives with the business logic and is testable without a database.
        """
        session = await self._users.get_session(session_id)
        if session is None:
            raise InvalidSession("Sesion desconocida.")
        if not session.is_active(datetime.now(timezone.utc)):
            raise InvalidSession("Sesion expirada o revocada.")
        return session

    async def user_of(self, session_id: UUID) -> User:
        session = await self.resolve_session(session_id)
        user = await self._users.find_by_id(session.user_id)
        if user is None:
            raise InvalidSession("El usuario de la sesion ya no existe.")
        return user
