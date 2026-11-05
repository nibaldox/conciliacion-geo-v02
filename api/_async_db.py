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
import os
import threading
import weakref
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, TypeVar

_T = TypeVar("_T")

DEFAULT_BLAST_CONCURRENCY = 2
_BLAST_CONCURRENCY_ENV = "CONCILIACION_BLAST_CONCURRENCY"
_BLAST_LIMITS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[int, asyncio.Semaphore]]" = (
    weakref.WeakKeyDictionary()
)
_BLAST_LIMITS_GUARD = threading.Lock()


def blast_concurrency_limit() -> int:
    """Return the heavy-blast concurrency limit, falling back to 2 when invalid."""
    raw = os.environ.get(_BLAST_CONCURRENCY_ENV)
    if raw is None:
        return DEFAULT_BLAST_CONCURRENCY
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_BLAST_CONCURRENCY
    return value if value > 0 else DEFAULT_BLAST_CONCURRENCY


def _blast_semaphore(limit: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    with _BLAST_LIMITS_GUARD:
        entry = _BLAST_LIMITS.get(loop)
        if entry is None or entry[0] != limit:
            entry = (limit, asyncio.Semaphore(limit))
            _BLAST_LIMITS[loop] = entry
        return entry[1]


@asynccontextmanager
async def blast_slot() -> AsyncIterator[None]:
    """Wait for one of the N heavy-blast slots without blocking the event loop."""
    semaphore = _blast_semaphore(blast_concurrency_limit())
    await semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


async def run_blast_limited(fn: Callable[..., _T], /, *args: Any) -> _T:
    """Run ``fn(*args)`` on the default executor while holding a blast slot."""
    async with blast_slot():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))


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
