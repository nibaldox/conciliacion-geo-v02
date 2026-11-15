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
from concurrent.futures import ThreadPoolExecutor
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


_UPLOAD_LIMITS = weakref.WeakKeyDictionary()
_UPLOAD_LIMITS_GUARD = threading.Lock()


@asynccontextmanager
async def upload_parse_slot() -> AsyncIterator[None]:
    from core import config

    limit = config.DEPLOY.upload_parse_concurrency
    loop = asyncio.get_running_loop()
    with _UPLOAD_LIMITS_GUARD:
        entry = _UPLOAD_LIMITS.get(loop)
        if entry is None or entry[0] != limit:
            entry = (limit, asyncio.Semaphore(limit))
            _UPLOAD_LIMITS[loop] = entry
        semaphore = entry[1]
    async with semaphore:
        yield


_PROCESS_LIMITS = weakref.WeakKeyDictionary()
_PROCESS_LIMITS_GUARD = threading.Lock()
_PROCESS_EXECUTOR = None
_PROCESS_EXECUTOR_LIMIT = None
_PROCESS_EXECUTOR_GUARD = threading.Lock()


@asynccontextmanager
async def process_slot() -> AsyncIterator[None]:
    from core import config

    limit = config.DEPLOY.process_concurrency
    loop = asyncio.get_running_loop()
    with _PROCESS_LIMITS_GUARD:
        entry = _PROCESS_LIMITS.get(loop)
        if entry is None or entry[0] != limit:
            entry = (limit, asyncio.Semaphore(limit))
            _PROCESS_LIMITS[loop] = entry
        semaphore = entry[1]
    async with semaphore:
        yield


def _process_executor(limit: int) -> ThreadPoolExecutor:
    global _PROCESS_EXECUTOR, _PROCESS_EXECUTOR_LIMIT
    with _PROCESS_EXECUTOR_GUARD:
        if _PROCESS_EXECUTOR is None or _PROCESS_EXECUTOR_LIMIT != limit:
            previous = _PROCESS_EXECUTOR
            _PROCESS_EXECUTOR = ThreadPoolExecutor(max_workers=limit, thread_name_prefix="pipeline")
            _PROCESS_EXECUTOR_LIMIT = limit
            if previous is not None:
                previous.shutdown(wait=False)
        return _PROCESS_EXECUTOR


async def run_process_limited(fn: Callable[..., _T], /, *args: Any) -> _T:
    from core import config

    async with process_slot():
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(_process_executor(config.DEPLOY.process_concurrency), fn, *args)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(future)
            finally:
                raise


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
