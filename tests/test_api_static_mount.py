"""Tests for api/main.py static mount of web/dist/ at /."""
import importlib
import importlib.util
import sys
from pathlib import Path


def _reload_main_with_fake_file(fake_main_path: Path):
    """Reload api.main with __file__ pointing to fake_main_path.

    The Python loader always sets module.__file__ from spec.origin BEFORE
    executing the module body, so a plain monkeypatch on __file__ is
    overwritten on reload. To control Path(__file__).parent.parent
    resolution, we read the real source from disk but compile and exec
    it in a fresh module namespace whose __file__ is the fake path.

    This mirrors the PyInstaller bundle layout (api/ and web/ are
    siblings under the project root) without depending on Path.cwd(),
    which is unreliable inside a frozen bundle.
    """
    import api  # ensure parent package is loaded

    real_main = Path(api.__file__).parent / "main.py"
    source = real_main.read_text(encoding="utf-8")

    # Drop any cached module so `from api.main import app` re-reads
    if "api.main" in sys.modules:
        del sys.modules["api.main"]
    parent = sys.modules.get("api")
    if parent is not None and hasattr(parent, "main"):
        delattr(parent, "main")

    # Build a spec that reports fake_main_path as the origin. Using
    # spec_from_loader with loader=None means we exec the compiled code
    # ourselves; this lets us pin __file__ to the fake path.
    spec = importlib.util.spec_from_loader(
        "api.main",
        loader=None,
        origin=str(fake_main_path),
    )
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(fake_main_path)
    module.__builtins__ = __builtins__
    sys.modules["api.main"] = module
    if parent is not None:
        setattr(parent, "main", module)

    code = compile(source, str(fake_main_path), "exec")
    exec(code, module.__dict__)
    return module


def test_static_mount_present_when_web_dist_exists(monkeypatch, tmp_path):
    # Set up fake package layout: <tmp>/api/main.py + <tmp>/web/dist/index.html
    fake_api = tmp_path / "api"
    fake_api.mkdir()
    (fake_api / "main.py").write_text("# placeholder for __file__ stub")
    fake_web_dist = tmp_path / "web" / "dist"
    fake_web_dist.mkdir(parents=True)
    (fake_web_dist / "index.html").write_text(
        "<html><body>ZZZ_FAKE_WEB_DIST_SENTINEL_42</body></html>"
    )

    api_main = _reload_main_with_fake_file(fake_api / "main.py")
    app = api_main.app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "ZZZ_FAKE_WEB_DIST_SENTINEL_42" in r.text


def test_static_mount_absent_when_web_dist_missing(monkeypatch, tmp_path):
    # Set up <tmp>/api/main.py with NO sibling web/dist/. The static
    # mount check fails and app.mount("/", ...) is not called.
    fake_api = tmp_path / "api"
    fake_api.mkdir()
    (fake_api / "main.py").write_text("# placeholder for __file__ stub")

    api_main = _reload_main_with_fake_file(fake_api / "main.py")
    app = api_main.app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code in (404, 405)
