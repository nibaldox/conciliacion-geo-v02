"""Tests for entry_api.resolve_data_dir() — pure platform/IO logic only."""
import sys
from pathlib import Path

import pytest


def test_resolve_data_dir_linux_with_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    if "entry_api" in sys.modules:
        del sys.modules["entry_api"]
    import entry_api
    result = entry_api.resolve_data_dir()
    assert result == tmp_path / "conciliacion"


def test_resolve_data_dir_linux_without_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    if "entry_api" in sys.modules:
        del sys.modules["entry_api"]
    import entry_api
    result = entry_api.resolve_data_dir()
    assert result == tmp_path / ".local" / "share" / "conciliacion"


def test_resolve_data_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    if "entry_api" in sys.modules:
        del sys.modules["entry_api"]
    import entry_api
    result = entry_api.resolve_data_dir()
    assert result == tmp_path / "conciliacion"


def test_resolve_data_dir_unsupported_platform(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    if "entry_api" in sys.modules:
        del sys.modules["entry_api"]
    import entry_api
    with pytest.raises(RuntimeError, match="Plataforma no soportada"):
        entry_api.resolve_data_dir()
