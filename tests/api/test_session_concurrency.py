"""Deterministic repro of the same-session-id creation race (T12 slice).

Two callers of ``api.database.get_or_create_session`` with the SAME new
session id both observe the row as absent, then both attempt the plain
INSERT. The interleaving is forced with a ``threading.Barrier`` placed
right after the SELECT ``fetchone()`` returned None — exercised through a
REAL sqlite3 connection wrapped by the factory installed over
``db.get_connection`` (no mocked results, no sleeps, no held writers).

Pre-fix expectation (RED): exactly one caller raises
``sqlite3.IntegrityError: UNIQUE constraint failed: sessions.id`` (or
``sqlite3.OperationalError: database is locked`` while the winner's write
transaction is still open), and connections are leaked on the error path.
"""

import sqlite3
import threading

import pytest

import api.database as db

SESSION_ID = "t12-race-session"
BARRIER_TIMEOUT = 10.0
JOIN_TIMEOUT = 15.0


def _real_connection():
    conn = sqlite3.connect(str(db.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class _BarrierCursor:
    """Real cursor; rendezvous with the other caller after a SELECT miss."""

    def __init__(self, real_cursor, barrier):
        self._real = real_cursor
        self._barrier = barrier

    def fetchone(self):
        row = self._real.fetchone()
        if row is None:
            self._barrier.wait(timeout=BARRIER_TIMEOUT)
        return row

    def __getattr__(self, name):
        return getattr(self._real, name)


class _BarrierConnection:
    """Real sqlite3 connection whose SELECT cursors are barrier-wrapped."""

    def __init__(self, real_conn, barrier):
        self._real = real_conn
        self._barrier = barrier

    def execute(self, sql, parameters=()):
        cursor = self._real.execute(sql, parameters)
        if "SELECT" in sql.upper():
            return _BarrierCursor(cursor, self._barrier)
        return cursor

    def __getattr__(self, name):
        return getattr(self._real, name)


class _RecordingConnection:
    """Real sqlite3 connection that records every executed statement."""

    def __init__(self, real_conn, statements):
        self._real = real_conn
        self._statements = statements

    def execute(self, sql, parameters=()):
        self._statements.append(sql)
        return self._real.execute(sql, parameters)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FailOnInsertConnection:
    """Real sqlite3 connection that fails the first INSERT (execute path)."""

    def __init__(self, real_conn, error):
        self._real = real_conn
        self._error = error

    def execute(self, sql, parameters=()):
        if "INSERT" in sql.upper():
            raise self._error
        return self._real.execute(sql, parameters)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FailOnCommitConnection:
    """Real sqlite3 connection whose commit() raises once (commit path)."""

    def __init__(self, real_conn, error):
        self._real = real_conn
        self._error = error

    def commit(self):
        raise self._error

    def __getattr__(self, name):
        return getattr(self._real, name)


def _run_callers(targets):
    threads = [threading.Thread(target=target) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=JOIN_TIMEOUT)
    assert not any(thread.is_alive() for thread in threads), (
        "callers did not finish within the time bound"
    )


def test_concurrent_same_new_id_both_callers_succeed(api_isolated_db, monkeypatch):
    """Both concurrent creators must return the id; exactly one row, with
    the default settings/sections intact (no overwrite, no duplicate)."""
    barrier = threading.Barrier(2)

    def factory():
        return _BarrierConnection(_real_connection(), barrier)

    monkeypatch.setattr(db, "get_connection", factory)

    results = []
    errors = []

    def caller():
        try:
            results.append(db.get_or_create_session(SESSION_ID))
        except BaseException as exc:
            errors.append(exc)

    _run_callers([caller, caller])

    assert errors == [], (
        "concurrent same-id creators raised: "
        f"{[f'{type(e).__name__}: {e}' for e in errors]}"
    )
    assert sorted(results) == [SESSION_ID, SESSION_ID]

    conn = _real_connection()
    try:
        rows = conn.execute(
            "SELECT id, settings, sections FROM sessions WHERE id = ?",
            (SESSION_ID,),
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["settings"] == "{}"
    assert rows[0]["sections"] == "[]"


def test_existing_session_read_fastpath_takes_no_write(api_isolated_db, monkeypatch):
    """An existing session keeps its settings/sections and the read fastpath
    performs no INSERT/UPDATE even under concurrent callers."""
    conn = _real_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (id, settings, sections) VALUES (?, ?, ?)",
            (SESSION_ID, '{"k": 1}', '[{"name": "s1"}]'),
        )
        conn.commit()
    finally:
        conn.close()

    statements = []

    def factory():
        return _RecordingConnection(_real_connection(), statements)

    monkeypatch.setattr(db, "get_connection", factory)

    results = []

    def caller():
        results.append(db.get_or_create_session(SESSION_ID))

    _run_callers([caller, caller])

    assert results == [SESSION_ID, SESSION_ID]
    writes = [s for s in statements if "INSERT" in s.upper() or "UPDATE" in s.upper()]
    assert writes == [], f"read fastpath performed writes: {writes!r}"
    assert db.get_settings(SESSION_ID) == {"k": 1}
    assert db.get_sections(SESSION_ID) == [{"name": "s1"}]


@pytest.mark.parametrize("failure_mode", ["insert_execute", "commit"])
def test_error_path_closes_connection_and_preserves_exception(
    api_isolated_db, monkeypatch, failure_mode
):
    """On an injected real-connection failure the original exception must
    propagate unchanged AND the connection must be closed (finally)."""
    error = RuntimeError(f"injected {failure_mode} failure")
    created = []

    def factory():
        real = _real_connection()
        created.append(real)
        if failure_mode == "insert_execute":
            return _FailOnInsertConnection(real, error)
        return _FailOnCommitConnection(real, error)

    monkeypatch.setattr(db, "get_connection", factory)

    with pytest.raises(RuntimeError) as excinfo:
        db.get_or_create_session(SESSION_ID)

    assert excinfo.value is error

    real = created[0]
    with pytest.raises(sqlite3.ProgrammingError):
        real.execute("SELECT 1")


def test_none_session_id_still_delegates_to_create_session(api_isolated_db, monkeypatch):
    """A missing session id must keep delegating to create_session()."""
    calls = []

    def fake_create_session():
        calls.append("called")
        return "delegated-session-id"

    monkeypatch.setattr(db, "create_session", fake_create_session)

    assert db.get_or_create_session(None) == "delegated-session-id"
    assert db.get_or_create_session("") == "delegated-session-id"
    assert calls == ["called", "called"]
