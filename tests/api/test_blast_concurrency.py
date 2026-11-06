"""Concurrency gate for the heavy /blast/* computations.

Several browser tabs firing /blast/holes/3d (and the correlation endpoints in
the process router) at once used to run one full parse + model build per
request, multiplying the memory peak. These tests pin the behaviour of the
``CONCILIACION_BLAST_CONCURRENCY`` gate: at most N heavy computations run at
the same time, extra requests wait and still answer 200, and an invalid value
falls back to the default (2).
"""

import asyncio
import threading
import time

import httpx
import pytest

import api.database as db
import api.routers.blast as blast_router
import api.routers.process as process_router
from api._async_db import blast_concurrency_limit, DEFAULT_BLAST_CONCURRENCY
from api.main import app

CONCURRENCY_ENV = "CONCILIACION_BLAST_CONCURRENCY"
HEAVY_DELAY_S = 0.15
N_REQUESTS = 4


class _ConcurrencyProbe:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.calls = 0

    def __enter__(self) -> "_ConcurrencyProbe":
        with self._lock:
            self.active += 1
            self.calls += 1
            self.max_active = max(self.max_active, self.active)
        return self

    def __exit__(self, *exc_info) -> None:
        with self._lock:
            self.active -= 1


def _wrap_heavy(monkeypatch, module, attribute, probe):
    original = getattr(module, attribute)

    def _slow(*args, **kwargs):
        with probe:
            time.sleep(HEAVY_DELAY_S)
            return original(*args, **kwargs)

    monkeypatch.setattr(module, attribute, _slow)
    return original


def _seed_session(session_id: str) -> None:
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {
        "accepted_rows": [
            {
                "hole_id": "BH-1", "source_row_index": 1,
                "X": 10, "Y": 20, "Z_collar": 100,
                "X_toe": 11, "Y_toe": 20, "Z_toe": 80,
            },
        ],
        "rejected_rows": [],
    })


async def _get_all(path: str, session_id: str, n: int = N_REQUESTS):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await asyncio.gather(*[
            client.get(path, headers={"X-Session-ID": session_id}) for _ in range(n)
        ])


@pytest.mark.asyncio
async def test_holes_3d_never_runs_more_than_one_heavy_build(client, monkeypatch):
    session_id = "blast-concurrency-limit-1"
    _seed_session(session_id)
    monkeypatch.setenv(CONCURRENCY_ENV, "1")
    probe = _ConcurrencyProbe()
    _wrap_heavy(monkeypatch, blast_router, "_build_holes_3d", probe)

    responses = await _get_all("/api/v1/blast/holes/3d", session_id)

    assert [r.status_code for r in responses] == [200] * N_REQUESTS
    assert probe.calls == N_REQUESTS
    assert probe.max_active == 1


@pytest.mark.asyncio
async def test_extra_requests_wait_instead_of_failing(client, monkeypatch):
    session_id = "blast-concurrency-queued"
    _seed_session(session_id)
    monkeypatch.setenv(CONCURRENCY_ENV, "1")
    probe = _ConcurrencyProbe()
    _wrap_heavy(monkeypatch, blast_router, "_build_holes_3d", probe)

    started = time.perf_counter()
    responses = await _get_all("/api/v1/blast/holes/3d", session_id, n=3)
    elapsed = time.perf_counter() - started

    assert all(r.status_code == 200 for r in responses)
    assert [r.json()["holes"][0]["hole_id"] for r in responses] == ["BH-1"] * 3
    assert elapsed >= HEAVY_DELAY_S * 3


@pytest.mark.asyncio
async def test_limit_defaults_to_two_when_env_is_invalid(client, monkeypatch):
    session_id = "blast-concurrency-invalid-env"
    _seed_session(session_id)
    monkeypatch.setenv(CONCURRENCY_ENV, "-3")
    assert blast_concurrency_limit() == DEFAULT_BLAST_CONCURRENCY == 2

    probe = _ConcurrencyProbe()
    _wrap_heavy(monkeypatch, blast_router, "_build_holes_3d", probe)

    responses = await _get_all("/api/v1/blast/holes/3d", session_id)

    assert [r.status_code for r in responses] == [200] * N_REQUESTS
    assert probe.calls == N_REQUESTS
    assert probe.max_active == DEFAULT_BLAST_CONCURRENCY


@pytest.mark.parametrize("raw", ["", "abc", "0", "-1", "1.5", " "])
def test_invalid_env_values_fall_back_to_default(monkeypatch, raw):
    monkeypatch.setenv(CONCURRENCY_ENV, raw)
    assert blast_concurrency_limit() == DEFAULT_BLAST_CONCURRENCY


def test_unset_env_uses_default(monkeypatch):
    monkeypatch.delenv(CONCURRENCY_ENV, raising=False)
    assert blast_concurrency_limit() == DEFAULT_BLAST_CONCURRENCY


def test_valid_env_value_is_used(monkeypatch):
    monkeypatch.setenv(CONCURRENCY_ENV, "5")
    assert blast_concurrency_limit() == 5


@pytest.mark.asyncio
async def test_blast_correlation_in_process_router_uses_the_same_gate(client, monkeypatch):
    session_id = "blast-concurrency-correlation"
    _seed_session(session_id)
    monkeypatch.setenv(CONCURRENCY_ENV, "1")
    probe = _ConcurrencyProbe()
    _wrap_heavy(monkeypatch, process_router, "_build_blast_correlation_sync", probe)

    responses = await _get_all("/api/v1/process/blast-correlation", session_id)

    assert [r.status_code for r in responses] == [200] * N_REQUESTS
    assert probe.calls == N_REQUESTS
    assert probe.max_active == 1
