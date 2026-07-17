"""Helpers for off-loading synchronous DB calls from async handlers.

The FastAPI handlers in ``api/routers/*.py`` expose ``async def`` endpoints
but the underlying SQLite access layer in ``api/database.py`` is purely
synchronous (it uses the stdlib ``sqlite3`` module, which is blocking).
Running those calls directly from the event loop would block the loop and
defeat the point of going async.

The :func:`run_db` helper schedules each call on the default thread-pool
executor (i.e. ``loop.run_in_executor(None, fn, *args, **kwargs)`` from
the brief) so the event loop stays responsive while the DB round-trip
completes on a worker thread. The default executor is shared with the
rest of Starlette/FastAPI, so we don't pay the cost of a separate pool.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, TypeVar

_T = TypeVar("_T")


def run_db(fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> Awaitable[_T]:
    """Schedule ``fn(*args, **kwargs)`` on the default thread-pool executor.

    Designed for ``async def`` FastAPI handlers that need to call the
    synchronous ``api.database`` helpers without blocking the event loop.
    The returned awaitable resolves to the wrapped function's return value.

    Example::

        session_id = await run_db(db.get_or_create_session, request.state.session_id)
        sections = await run_db(db.get_sections, session_id)
    """
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, lambda: fn(*args, **kwargs))
