"""Tests for the AI conversation cleanup: startup purge + periodic task.

Drives the REAL ``api.main.lifespan`` and the REAL periodic helper with
the DB layer faked and ``run_db`` resolved synchronously: no SQLite
file, no thread pool, no real sleeps (the periodic interval is shrunk
to milliseconds when the purge cadence itself is under test). Verifies
the startup purge runs exactly once, the periodic helper purges with
``CONVERSATION_TTL_HOURS`` and exits promptly on a pre-set stop event
without purging, a failing purge never kills the loop, and the
lifespan stops both cleanup tasks cleanly.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest

import api.database as db
import api.dxf_uploads as dxf_uploads
import api.main as api_main
from api.ai_agent_conversations import CONVERSATION_TTL_HOURS
from api.main import lifespan


def install_cleanup_fakes(
    monkeypatch: pytest.MonkeyPatch,
    purges: list[Any],
) -> None:
    """Route every lifespan cleanup seam into in-memory fakes."""
    monkeypatch.setattr(api_main, "init_db", lambda: None)
    monkeypatch.setattr(api_main, "open_sentinel", lambda: None)
    monkeypatch.setattr(api_main, "close_sentinel", lambda: None)

    def fake_purge(max_age_hours: int) -> int:
        purges.append(max_age_hours)
        return 0

    monkeypatch.setattr(db, "delete_old_ai_conversations", fake_purge)
    monkeypatch.setattr(dxf_uploads, "cleanup_expired", lambda: None)
    monkeypatch.setattr(dxf_uploads, "cleanup_all", lambda: None)
    monkeypatch.setattr(api_main, "cleanup_old_sessions", lambda *args: None)

    async def fake_run_db(
        fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> Any:
        return fn(*args, **kwargs)

    monkeypatch.setattr(api_main, "run_db", fake_run_db)


@pytest.mark.asyncio
async def test_lifespan_purges_once_at_startup_and_stops_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purges: list[Any] = []
    install_cleanup_fakes(monkeypatch, purges)
    cm = lifespan(api_main.app)
    await asyncio.wait_for(cm.__aenter__(), timeout=5)
    await asyncio.sleep(0.05)
    assert purges == [CONVERSATION_TTL_HOURS]
    await asyncio.wait_for(cm.__aexit__(None, None, None), timeout=5)
    assert purges == [CONVERSATION_TTL_HOURS]
    leftover = [
        task
        for task in asyncio.all_tasks()
        if "cleanup_ai_conversations_periodic" in repr(task.get_coro())
        or "cleanup_pending_imports" in repr(task.get_coro())
    ]
    assert leftover == []


@pytest.mark.asyncio
async def test_periodic_helper_purges_with_ttl_and_keeps_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purges: list[Any] = []
    install_cleanup_fakes(monkeypatch, purges)
    monkeypatch.setattr(api_main, "AI_CONVERSATION_CLEANUP_INTERVAL_S", 0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(
        api_main.cleanup_ai_conversations_periodic(stop)
    )
    await asyncio.sleep(0.08)
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert task.exception() is None
    assert len(purges) >= 2
    assert all(ttl == CONVERSATION_TTL_HOURS for ttl in purges)


@pytest.mark.asyncio
async def test_periodic_helper_exits_promptly_on_preset_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purges: list[Any] = []
    install_cleanup_fakes(monkeypatch, purges)
    stop = asyncio.Event()
    stop.set()
    started = time.perf_counter()
    await asyncio.wait_for(
        api_main.cleanup_ai_conversations_periodic(stop), timeout=2
    )
    assert time.perf_counter() - started < 1.0
    assert purges == []


@pytest.mark.asyncio
async def test_periodic_helper_survives_a_failing_purge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_cleanup_fakes(monkeypatch, [])
    attempts: list[int] = []

    def flaky_purge(max_age_hours: int) -> int:
        attempts.append(max_age_hours)
        if len(attempts) == 1:
            raise RuntimeError("purge boom")
        return 0

    monkeypatch.setattr(db, "delete_old_ai_conversations", flaky_purge)
    monkeypatch.setattr(api_main, "AI_CONVERSATION_CLEANUP_INTERVAL_S", 0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(
        api_main.cleanup_ai_conversations_periodic(stop)
    )
    await asyncio.sleep(0.08)
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert task.exception() is None
    assert len(attempts) >= 2
