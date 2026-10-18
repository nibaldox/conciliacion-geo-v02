"""Durabilidad SQLite: PRAGMA synchronous=NORMAL y conexión centinela.

Regresión para el bloqueo de escritura observado en btrfs: sin la
conexión centinela, el último cierre de conexión ejecutaba
``sqlite3WalClose -> checkpoint`` (fsync) y borraba el ``-wal`` en cada
request, dejando el lock de escritura tomado más allá del busy_timeout
de 5 s y produciendo errores 'database is locked'.
"""

from pathlib import Path

import pytest
import sqlite3

from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(autouse=True)
def _close_sentinel_after_test():
    """Garantiza que el centinela no sobreviva al test."""
    yield
    import api.database as db

    close = getattr(db, "close_sentinel", None)
    if close is not None:
        close()


def test_connection_pragmas_are_normal_and_wal(api_isolated_db):
    """Toda conexión de get_connection() usa synchronous=NORMAL y WAL."""
    import api.database as db

    conn = db.get_connection()
    try:
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_wal_survives_while_lifespan_active(api_isolated_db):
    """Con el lifespan activo el archivo -wal persiste tras cada request."""
    import api.database as db

    wal = Path(f"{db.DB_PATH}-wal")
    with TestClient(app) as client:
        assert db._sentinel is not None
        resp = client.get(
            "/api/v1/settings",
            headers={"X-Session-ID": "sentinel-wal-check"},
        )
        assert resp.status_code == 200
        assert wal.exists()
        assert db._sentinel is not None


def test_sentinel_closed_and_wal_removed_after_lifespan(api_isolated_db):
    """Al salir el lifespan el centinela se cierra y el -wal se limpia."""
    import api.database as db

    wal = Path(f"{db.DB_PATH}-wal")
    with TestClient(app) as client:
        assert client.get(
            "/api/v1/settings",
            headers={"X-Session-ID": "sentinel-close-check"},
        ).status_code == 200
        assert wal.exists()
    assert db._sentinel is None
    assert not wal.exists()
    db.close_sentinel()


def test_open_close_sentinel_idempotent_and_rebinds(tmp_path, monkeypatch, api_isolated_db):
    """open/close_sentinel son idempotentes y reabren sobre el DB_PATH actual."""
    import api.database as db

    first = db.open_sentinel()
    assert db.open_sentinel() is first
    db.close_sentinel()
    db.close_sentinel()
    assert db._sentinel is None
    with pytest.raises(sqlite3.ProgrammingError):
        first.execute("SELECT 1")

    db.open_sentinel()
    previous = db._sentinel
    new_db = tmp_path / "rebound" / "test.db"
    monkeypatch.setattr(db, "DB_PATH", new_db)
    db.init_db()
    rebound = db.open_sentinel()
    assert rebound is not previous
    with pytest.raises(sqlite3.ProgrammingError):
        previous.execute("SELECT 1")
    assert rebound.execute("SELECT 1").fetchone()[0] == 1

    writer = db.get_connection()
    writer.execute("INSERT INTO sessions (id) VALUES ('rebound')")
    writer.commit()
    writer.close()
    assert Path(f"{new_db}-wal").exists()
    assert rebound.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
