"""One turn end to end, including what gets persisted."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from models.auth import User
from models.conversation import RouteDecision
from services.chat_service import ConversationForbidden, ConversationNotFound


def _user(name: str = "Ana") -> User:
    """A registered person, as the session would hand it to the service."""
    return User(
        id=uuid4(),
        cedula=f"10{uuid4().int % 10**8:08d}",
        display_name=name,
        created_at=datetime.now(timezone.utc),
    )


async def test_a_turn_persists_both_sides(chat_service, conversations):
    user = _user()

    result = await chat_service.send(user, "cual es el horario de atencion")

    stored = await conversations.history(result.conversation_id)
    assert [m.role for m in stored] == ["user", "agent"]
    assert stored[0].content == "cual es el horario de atencion"
    assert stored[1].content == result.reply


async def test_the_agent_message_records_its_decision(chat_service, conversations):
    user = _user()

    result = await chat_service.send(user, "cual es el horario de atencion")

    agent_message = (await conversations.history(result.conversation_id))[1]
    assert agent_message.intent == "horario"
    assert agent_message.route == str(RouteDecision.ANSWER)
    # El corpus de prueba tiene menos documentos que top_k, asi que vuelven
    # todos. Lo que importa es que la fuente correcta quede registrada.
    assert "horarios.md" in agent_message.sources


async def test_omitting_conversation_id_starts_a_new_one(chat_service):
    user = _user()

    first = await chat_service.send(user, "hola")
    second = await chat_service.send(user, "hola otra vez")

    assert first.conversation_id != second.conversation_id


async def test_passing_conversation_id_continues_the_same_thread(chat_service):
    user = _user()

    first = await chat_service.send(user, "cual es el horario")
    second = await chat_service.send(
        user, "y los canales", conversation_id=first.conversation_id
    )

    assert second.conversation_id == first.conversation_id
    assert second.thread_id == first.thread_id


async def test_history_accumulates_across_turns(chat_service, conversations):
    user = _user()

    first = await chat_service.send(user, "cual es el horario")
    await chat_service.send(user, "y los canales", conversation_id=first.conversation_id)

    assert len(await conversations.history(first.conversation_id)) == 4


async def test_cannot_write_into_someone_elses_conversation(chat_service):
    """Guessing a UUID must not grant access to another user's thread."""
    owner = await chat_service.send(_user(), "hola")

    with pytest.raises(ConversationForbidden):
        await chat_service.send(_user(), "intruso", conversation_id=owner.conversation_id)


async def test_cannot_read_someone_elses_history(chat_service):
    owner = await chat_service.send(_user(), "hola")

    with pytest.raises(ConversationForbidden):
        await chat_service.history(uuid4(), owner.conversation_id)


async def test_unknown_conversation_is_reported_as_missing(chat_service):
    with pytest.raises(ConversationNotFound):
        await chat_service.send(_user(), "hola", conversation_id=uuid4())


async def test_listing_only_returns_your_own(chat_service):
    mine, theirs = _user(), _user()
    await chat_service.send(mine, "hola")
    await chat_service.send(theirs, "hola")

    listed = await chat_service.list_conversations(mine.id)

    assert len(listed) == 1
    assert listed[0].user_id == mine.id
