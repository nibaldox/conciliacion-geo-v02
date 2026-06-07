"""Tests for api/main.py static mount of web/dist/ at /."""
import importlib
import sys


def _reload_main_module():
    """Reimport api.main so the static-mount check re-runs.

    Same cleanup pattern as test_database_env.py: on Python 3.14+ the
    parent package caches submodules as attributes, so just deleting
    from sys.modules is not enough. The package attribute must be
    cleared too, otherwise `from api.main import app` returns the
    stale module / old app.
    """
    if "api.main" in sys.modules:
        del sys.modules["api.main"]
    parent = sys.modules.get("api")
    if parent is not None and hasattr(parent, "main"):
        delattr(parent, "main")
    return importlib.import_module("api.main")


def test_static_mount_present_when_web_dist_exists(monkeypatch, tmp_path):
    web_dist = tmp_path / "web" / "dist"
    web_dist.mkdir(parents=True)
    (web_dist / "index.html").write_text("<html><body>hi</body></html>")

    monkeypatch.chdir(tmp_path)
    api_main = _reload_main_module()
    app = api_main.app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "hi" in r.text


def test_static_mount_absent_when_web_dist_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    api_main = _reload_main_module()
    app = api_main.app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code in (404, 405)
