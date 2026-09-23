"""Platform quirks that every async entry point has to deal with.

Right now there is exactly one, but it is not optional: psycopg refuses to run
on Windows' default event loop, so anything that touches the database
asynchronously has to fix the policy before the loop is created.
"""

from __future__ import annotations

import asyncio
import sys


def ensure_psycopg_compatible_event_loop() -> None:
    """Switch Windows to the selector event loop.

    Since Python 3.8, Windows defaults to ``ProactorEventLoop``, and psycopg3
    raises outright on it:

        psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to
        run in async mode.

    The symptom is confusing -- a connection pool that simply never finishes
    opening, while a synchronous connection to the same database works fine --
    so this is called explicitly from every async entry point rather than left
    for somebody to rediscover.

    No-op on Linux and macOS, where the default loop is already compatible.
    """
    if sys.platform != "win32":
        return

    policy = asyncio.get_event_loop_policy()
    if isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy):
        return

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def new_selector_event_loop() -> asyncio.AbstractEventLoop:
    """Event loop factory for uvicorn's ``loop`` option.

    Since 0.36, uvicorn runs the server as::

        asyncio.run(server.serve(), loop_factory=config.get_loop_factory())

    A ``loop_factory`` bypasses the event loop policy entirely, which is why
    calling ``ensure_psycopg_compatible_event_loop()`` before ``uvicorn.run``
    has no effect. The supported way in is ``Config(loop="module:callable")``,
    and this is that callable.

    Because it goes through the config, reload subprocesses get it too.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def assert_event_loop_is_usable() -> None:
    """Fail fast, and legibly, if we are already on the wrong loop.

    Called once at startup. Without it, running the app under a Proactor loop
    produces a connection pool that hangs until timeout and an error message
    that says nothing about the real cause.

    The policy cannot be fixed from here: by the time this runs the loop
    already exists, so the only useful thing to do is say what went wrong and
    how to start the server correctly.
    """
    if sys.platform != "win32":
        return

    loop = asyncio.get_running_loop()
    if type(loop).__name__ == "ProactorEventLoop":
        raise RuntimeError(
            "Esta corriendo sobre ProactorEventLoop y psycopg no lo soporta.\n"
            "En Windows arranca el servidor con:\n"
            "    python -m scripts.serve\n"
            "en vez de invocar uvicorn directamente: uvicorn crea el event loop "
            "antes de importar la app, asi que arreglar la politica desde "
            "api/main.py llegaria tarde."
        )
