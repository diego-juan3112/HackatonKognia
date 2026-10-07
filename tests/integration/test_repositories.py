"""The PostgreSQL repositories against a real database.

Covers what the in-memory doubles only simulate: real constraints, real
cascades, real transactions.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from models.auth import UserAlreadyExists

pytestmark = pytest.mark.integration


# --- users -----------------------------------------------------------------


async def test_create_then_find_by_cedula(users):
    created = await users.create("1053812345", "Juan")

    found = await users.find_by_cedula("1053812345")

    assert found is not None
    assert found.id == created.id
    assert found.display_name == "Juan"


async def test_duplicate_cedula_is_rejected_by_the_database(users):
    """The UNIQUE constraint is what stops one person becoming two rows."""
    await users.create("1053812345")

    with pytest.raises(UserAlreadyExists):
        await users.create("1053812345")


async def test_unknown_cedula_returns_none(users):
    assert await users.find_by_cedula("0000000000") is None


async def test_session_round_trip(users):
    user = await users.create("1053812345")

    session = await users.create_session(user.id, ttl_hours=12)
    fetched = await users.get_session(session.id)

    assert fetched is not None
    assert fetched.user_id == user.id
    assert fetched.expires_at > fetched.created_at


async def test_touch_last_seen_updates_the_column(users):
    user = await users.create("1053812345")
    assert user.last_seen_at is None

    await users.touch_last_seen(user.id)

    assert (await users.find_by_id(user.id)).last_seen_at is not None


# --- conversations ---------------------------------------------------------


async def test_conversation_and_message_round_trip(users, conversations):
    user = await users.create("1053812345")
    conversation = await conversations.create(user.id, domain="faq_demo")

    await conversations.append_message(conversation.id, "user", "hola")
    await conversations.append_message(
        conversation.id, "agent", "buenas", intent="saludo", sources=["a.md"]
    )

    history = await conversations.history(conversation.id)

    assert [m.role for m in history] == ["user", "agent"]
    assert history[1].intent == "saludo"
    assert history[1].sources == ["a.md"], "JSONB debe volver como lista"


async def test_appending_a_message_moves_updated_at(users, conversations):
    user = await users.create("1053812345")
    conversation = await conversations.create(user.id, domain="faq_demo")
    before = conversation.updated_at

    await conversations.append_message(conversation.id, "user", "hola")

    assert (await conversations.get(conversation.id)).updated_at > before


async def test_listing_is_scoped_to_the_user(users, conversations):
    mine = await users.create("1053812345")
    theirs = await users.create("9998887777")
    await conversations.create(mine.id, domain="faq_demo")
    await conversations.create(theirs.id, domain="faq_demo")

    listed = await conversations.list_for_user(mine.id)

    assert len(listed) == 1
    assert listed[0].user_id == mine.id


async def test_deleting_a_user_cascades_to_conversations(users, conversations, pool):
    user = await users.create("1053812345")
    conversation = await conversations.create(user.id, domain="faq_demo")
    await conversations.append_message(conversation.id, "user", "hola")

    async with pool.connection() as conn:
        await conn.execute("DELETE FROM users WHERE id = %s", (user.id,))

    assert await conversations.get(conversation.id) is None
    assert await conversations.history(conversation.id) == []


async def test_unknown_conversation_returns_none(conversations):
    assert await conversations.get(uuid4()) is None
