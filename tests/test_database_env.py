"""Tests for api/database.py honoring CONCILIACION_DATA_DIR env var."""
import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest


def _reload_database_module():
    """Reimport api.database so module-level DB_PATH is recomputed.

    Uses :func:`importlib.reload` so the EXISTING module object is updated
    in place — every other module that did ``import api.database as db``
    (e.g. ``api.routers.blast``) keeps a single, consistent reference.
    The previous ``del sys.modules[...]`` approach created a NEW module
    object and silently broke downstream callers (their ``db`` kept
    pointing at the stale one), which surfaced as order-dependent
    failures in unrelated tests.
    """
    if "api.database" in sys.modules:
        return importlib.reload(sys.modules["api.database"])
    return importlib.import_module("api.database")


@pytest.fixture(autouse=True)
def _restore_db_path_after_reload(monkeypatch):
    """Restore the default DB_PATH after the reload-based tests.

    ``importlib.reload`` re-runs the module body and recomputes
    ``DB_PATH`` from the active ``CONCILIACION_DATA_DIR`` env var. Even
    after the monkeypatch teardown restores the env, the module-level
    constant stays at the reloaded value. We reload ONCE MORE on the way
    out (with the original env restored) so subsequent tests see a
    consistent default path.
    """
    yield
    # Restore: with the env now reverted, reload so DB_PATH points back
    # at the package default (<repo>/data/conciliacion.db).
    try:
        importlib.reload(sys.modules["api.database"])
    except Exception:
        pass


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
