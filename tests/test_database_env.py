"""Tests for api/database.py honoring CONCILIACION_DATA_DIR env var."""
import importlib
import os
import sys
import tempfile
from pathlib import Path


def _reload_database_module():
    """Reimport api.database so module-level DB_PATH is recomputed.

    On Python 3.14+ the parent package caches submodules as attributes,
    so just deleting from sys.modules is not enough — the package
    attribute must be cleared too, otherwise `from api import database`
    returns the stale module.
    """
    if "api.database" in sys.modules:
        del sys.modules["api.database"]
    parent = sys.modules.get("api")
    if parent is not None and hasattr(parent, "database"):
        delattr(parent, "database")
    return importlib.import_module("api.database")


def test_db_path_uses_default_when_env_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("CONCILIACION_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    database = _reload_database_module()
    # Default is <repo>/data relative to the package
    assert database.DB_PATH.name == "conciliacion.db"
    assert database.DB_PATH.parent.name == "data"


def test_db_path_uses_env_var_when_set(monkeypatch, tmp_path):
    custom = tmp_path / "custom_data"
    monkeypatch.setenv("CONCILIACION_DATA_DIR", str(custom))
    database = _reload_database_module()
    assert database.DB_PATH == custom / "conciliacion.db"
