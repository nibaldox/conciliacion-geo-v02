"""Tests for startup VACUUM of the SQLite database and its env-driven config."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import api.database as db
import api.main as main_module

MIB = 2**20


def _build_db(path: Path, keep_mb: int, free_mb: int) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE blob_store (id INTEGER PRIMARY KEY, payload BLOB)")
    conn.execute("CREATE TABLE keep (id INTEGER PRIMARY KEY, value TEXT)")
    chunk = os.urandom(MIB)
    for _ in range(keep_mb):
        conn.execute("INSERT INTO blob_store(payload) VALUES (?)", (chunk,))
    for _ in range(free_mb):
        conn.execute("INSERT INTO blob_store(payload) VALUES (?)", (chunk,))
    conn.execute("INSERT INTO keep(value) VALUES ('alpha'), ('beta')")
    conn.commit()
    conn.execute("DELETE FROM blob_store WHERE id > ?", (keep_mb,))
    conn.commit()
    conn.close()


def _freelist_count(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("PRAGMA freelist_count").fetchone()[0]
    finally:
        conn.close()


def _keep_values(path: Path) -> list[str]:
    conn = sqlite3.connect(str(path))
    try:
        return [row[0] for row in conn.execute("SELECT value FROM keep ORDER BY id")]
    finally:
        conn.close()


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "conciliacion.db")
    yield tmp_path


class TestVacuumIfFragmented:
    def test_vacuums_when_free_space_exceeds_thresholds(self, data_dir: Path) -> None:
        path = db.DB_PATH
        _build_db(path, keep_mb=1, free_mb=10)
        size_before = path.stat().st_size
        assert _freelist_count(path) > 0

        result = db.vacuum_if_fragmented(min_free_ratio=0.5, min_free_mb=1)

        assert result["status"] == "vacuumed"
        assert result["reason"]
        assert result["size_before_mb"] == pytest.approx(size_before / MIB, rel=1e-3)
        assert result["size_after_mb"] < result["size_before_mb"]
        assert result["free_ratio"] >= 0.5
        assert result["free_mb"] >= 1
        assert result["duration_s"] >= 0
        assert path.stat().st_size < size_before
        assert _freelist_count(path) == 0
        assert _keep_values(path) == ["alpha", "beta"]

    def test_truncates_wal_after_vacuum(self, data_dir: Path) -> None:
        path = db.DB_PATH
        _build_db(path, keep_mb=1, free_mb=10)

        db.vacuum_if_fragmented(min_free_ratio=0.5, min_free_mb=1)

        wal = Path(str(path) + "-wal")
        assert not wal.exists() or wal.stat().st_size == 0

    def test_skipped_below_free_ratio_threshold(self, data_dir: Path) -> None:
        path = db.DB_PATH
        _build_db(path, keep_mb=10, free_mb=1)
        size_before = path.stat().st_size

        result = db.vacuum_if_fragmented(min_free_ratio=0.5, min_free_mb=0.5)

        assert result["status"] == "skipped"
        assert "ratio" in result["reason"]
        assert result["free_ratio"] < 0.5
        assert path.stat().st_size == size_before

    def test_skipped_below_free_mb_threshold(self, data_dir: Path) -> None:
        path = db.DB_PATH
        _build_db(path, keep_mb=0, free_mb=1)
        size_before = path.stat().st_size

        result = db.vacuum_if_fragmented(min_free_ratio=0.5, min_free_mb=256)

        assert result["status"] == "skipped"
        assert "mb" in result["reason"]
        assert result["free_ratio"] >= 0.5
        assert result["free_mb"] < 256
        assert path.stat().st_size == size_before

    def test_missing_database_is_skipped_and_not_created(self, data_dir: Path) -> None:
        path = db.DB_PATH
        assert not path.exists()

        result = db.vacuum_if_fragmented(min_free_ratio=0.5, min_free_mb=1)

        assert result["status"] == "skipped"
        assert result["reason"] == "no_database"
        assert not path.exists()

    def test_sqlite_error_returns_failed_without_raising(
        self, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _build_db(db.DB_PATH, keep_mb=1, free_mb=10)

        def broken_connection():
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(db, "get_connection", broken_connection)

        result = db.vacuum_if_fragmented(min_free_ratio=0.5, min_free_mb=1)

        assert result["status"] == "failed"
        assert result["reason"] == "OperationalError"

    def test_os_error_returns_failed_without_raising(
        self, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _build_db(db.DB_PATH, keep_mb=1, free_mb=10)

        def broken_stat(*_args, **_kwargs):
            raise OSError("stat failed")

        monkeypatch.setattr(db.os.path, "getsize", broken_stat)

        result = db.vacuum_if_fragmented(min_free_ratio=0.5, min_free_mb=1)

        assert result["status"] == "failed"
        assert result["reason"] == "OSError"


class TestStorageMaintenanceConfig:
    def _load(self, monkeypatch: pytest.MonkeyPatch, **env: str):
        from core.config import StorageMaintenanceDefaults

        for name in (
            "CONCILIACION_VACUUM_ON_STARTUP",
            "CONCILIACION_VACUUM_MIN_FREE_RATIO",
            "CONCILIACION_VACUUM_MIN_FREE_MB",
        ):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return StorageMaintenanceDefaults()

    def test_defaults_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = self._load(monkeypatch)

        assert cfg.vacuum_on_startup is True
        assert cfg.vacuum_min_free_ratio == 0.5
        assert cfg.vacuum_min_free_mb == 256.0

    def test_valid_env_values_are_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = self._load(
            monkeypatch,
            CONCILIACION_VACUUM_ON_STARTUP="false",
            CONCILIACION_VACUUM_MIN_FREE_RATIO="0.7",
            CONCILIACION_VACUUM_MIN_FREE_MB="64",
        )

        assert cfg.vacuum_on_startup is False
        assert cfg.vacuum_min_free_ratio == 0.7
        assert cfg.vacuum_min_free_mb == 64.0

    def test_ratio_boundary_one_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = self._load(monkeypatch, CONCILIACION_VACUUM_MIN_FREE_RATIO="1")

        assert cfg.vacuum_min_free_ratio == 1.0

    @pytest.mark.parametrize("raw", ["abc", "0", "-0.2", "1.5", "nan", "inf", ""])
    def test_invalid_ratio_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        cfg = self._load(monkeypatch, CONCILIACION_VACUUM_MIN_FREE_RATIO=raw)

        assert cfg.vacuum_min_free_ratio == 0.5

    @pytest.mark.parametrize("raw", ["-5", "abc", "nan", "inf"])
    def test_invalid_mb_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        cfg = self._load(monkeypatch, CONCILIACION_VACUUM_MIN_FREE_MB=raw)

        assert cfg.vacuum_min_free_mb == 256.0

    def test_zero_mb_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = self._load(monkeypatch, CONCILIACION_VACUUM_MIN_FREE_MB="0")

        assert cfg.vacuum_min_free_mb == 0.0

    def test_singleton_is_exported_from_config(self) -> None:
        from core.config import STORAGE_MAINTENANCE, StorageMaintenanceDefaults

        assert isinstance(STORAGE_MAINTENANCE, StorageMaintenanceDefaults)


class TestLifespanStartupVacuum:
    @pytest.fixture()
    def app_data_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setenv("CONCILIACION_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(db, "DB_PATH", tmp_path / "conciliacion.db")
        return tmp_path

    def _config(self, **overrides):
        from core.config import StorageMaintenanceDefaults

        return StorageMaintenanceDefaults(**overrides)

    def test_not_called_when_disabled(
        self, app_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple] = []

        def spy(*args):
            calls.append(args)
            return {"status": "skipped", "reason": "x"}

        monkeypatch.setattr(main_module, "vacuum_if_fragmented", spy)
        monkeypatch.setattr(
            main_module, "STORAGE_MAINTENANCE", self._config(vacuum_on_startup=False)
        )

        with TestClient(main_module.app):
            pass

        assert calls == []

    def test_called_once_with_configured_thresholds(
        self, app_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple] = []

        def spy(*args):
            calls.append(args)
            return {"status": "skipped", "reason": "no_database"}

        monkeypatch.setattr(main_module, "vacuum_if_fragmented", spy)
        monkeypatch.setattr(
            main_module,
            "STORAGE_MAINTENANCE",
            self._config(
                vacuum_on_startup=True, vacuum_min_free_ratio=0.3, vacuum_min_free_mb=12.0
            ),
        )

        with TestClient(main_module.app):
            pass

        assert calls == [(0.3, 12.0)]

    def test_failed_result_does_not_block_startup(
        self, app_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def spy(*_args):
            return {"status": "failed", "reason": "OperationalError"}

        monkeypatch.setattr(main_module, "vacuum_if_fragmented", spy)
        monkeypatch.setattr(
            main_module, "STORAGE_MAINTENANCE", self._config(vacuum_on_startup=True)
        )

        with TestClient(main_module.app) as client:
            response = client.get("/api/v1/health")

        assert response.status_code == 200

    def test_raising_vacuum_does_not_block_startup(
        self, app_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def spy(*_args):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(main_module, "vacuum_if_fragmented", spy)
        monkeypatch.setattr(
            main_module, "STORAGE_MAINTENANCE", self._config(vacuum_on_startup=True)
        )

        with TestClient(main_module.app) as client:
            response = client.get("/api/v1/health")

        assert response.status_code == 200
