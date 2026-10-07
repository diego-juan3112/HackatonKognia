"""Identity data shapes.

Identification is by cedula with no password. That is a deliberate scope
decision for the demo, not an oversight -- see decision D-06 in docs/00-contexto-y-decisiones.md. Anyone who
knows a cedula can impersonate that user, so nothing sensitive should be
exposed through these endpoints until real authentication exists.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class User(BaseModel):
    """A person identified by their national id."""

    id: UUID
    cedula: str
    display_name: str | None = None
    created_at: datetime
    last_seen_at: datetime | None = None


class Session(BaseModel):
    """A time-boxed handle the client sends back on every request."""

    id: UUID
    user_id: UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


class Identification(BaseModel):
    """What the client gets back after identifying itself."""

    user_id: UUID
    session_id: UUID
    cedula: str
    display_name: str | None = None
    expires_at: datetime


class Conversation(BaseModel):
    """One chat thread belonging to a user."""

    id: UUID
    user_id: UUID
    thread_id: str = Field(description="The key LangGraph's checkpointer resumes state by.")
    title: str | None = None
    domain: str
    created_at: datetime
    updated_at: datetime


class MessageRecord(BaseModel):
    """One persisted turn, as stored in the ``messages`` table.

    Distinct from the LangChain message objects that travel inside the graph:
    this is the readable, queryable record, with the routing decision attached.
    """

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    intent: str | None = None
    route: str | None = None
    sources: list[str] = Field(default_factory=list)
    created_at: datetime


class UserAlreadyExists(Exception):
    """A user with that cedula is already registered.

    Declared here rather than raised as a database error so that services/ and
    api/ can react to it without knowing that PostgreSQL exists.
    """
