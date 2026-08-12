"""Regression tests for the Docker Compose "API unhealthy" failure (PR #19).

Root cause
----------
``api/database.py`` does ``from core import load_mesh`` at module top
level. That triggers ``core/__init__.py`` → ``core.mesh_handler``, whose
first lines include ``import plotly.graph_objects as go``. ``plotly`` is
only used by :func:`core.mesh_handler.mesh_to_plotly` (a visualization
helper the API never calls), but the import fires at module load anyway.

``requirements-api.txt`` deliberately excludes UI deps (Streamlit/Plotly),
so the API Docker image had no plotly. uvicorn then crashed during
``import api.main`` with ``ModuleNotFoundError: No module named 'plotly'``,
the process died, the container restarted in a loop and Docker marked it
``unhealthy`` — which is exactly what the CI smoke test reported.

The fix lives in ``Dockerfile-api`` (install plotly into the runtime venv
and set ``MPLCONFIGDIR`` for the non-root user). These tests pin both
invariants so the regression cannot be silently reintroduced.
"""
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOCKERFILE = _REPO_ROOT / "Dockerfile-api"


def _read_dockerfile() -> str:
    assert _DOCKERFILE.exists(), f"Dockerfile-api missing at {_DOCKERFILE}"
    return _DOCKERFILE.read_text(encoding="utf-8")


class TestDockerfileApiRuntimeDeps:
    def test_dockerfile_installs_plotly(self):
        """The API image must install plotly.

        ``core/mesh_handler`` imports it at module top level; without it,
        ``import api.main`` raises ModuleNotFoundError and uvicorn dies,
        so the container never becomes healthy.
        """
        content = _read_dockerfile()
        assert "plotly" in content, (
            "Dockerfile-api no instala plotly. core/mesh_handler.py lo "
            "importa en cabezera y la cadena api.database -> core.__init__ "
            "lo requiere: sin plotly, uvicorn muere al arrancar y el "
            "healthcheck del contenedor nunca pasa (unhealthy)."
        )

    def test_dockerfile_sets_mplconfigdir(self):
        """The conciliacion user has no home dir; matplotlib needs a
        writable cache path or it falls back to /tmp with a warning
        (slow import + multiprocessing issues in clean containers)."""
        content = _read_dockerfile()
        assert "MPLCONFIGDIR" in content, (
            "Dockerfile-api debe definir MPLCONFIGDIR: el usuario "
            "conciliacion se crea con --no-create-home, por lo que "
            "matplotlib no puede escribir ~/.config/matplotlib."
        )


class TestRootCausePlotlyTransitiveImport:
    """Demonstrates the actual root cause in a clean subprocess."""

    def test_api_import_fails_when_plotly_blocked(self):
        """When plotly is unimportable, ``import api.main`` fails.

        This reproduces the Docker failure deterministically: the API-only
        environment (requirements-api.txt, no plotly) cannot import the
        backend at all. It is the inverse of
        :meth:`TestImportSmoke.test_api_imports_without_reportlab` —
        plotly is NOT optional for the current import graph.
        """
        code = """
import sys

class _BlockPlotly:
    # Modern PEP 451 finder: find_spec replaces the deprecated find_module.
    def find_spec(self, name, path=None, target=None):
        if name == "plotly" or name.startswith("plotly."):
            raise ImportError(f"plotly blocked for test: {name}")
        return None

    # Back-compat shim for interpreters that still call find_module.
    def find_module(self, name, path=None):
        if name == "plotly" or name.startswith("plotly."):
            raise ImportError(f"plotly blocked for test: {name}")
        return None

sys.meta_path.insert(0, _BlockPlotly())
try:
    import api.main  # noqa: F401
except ImportError as exc:
    if "plotly" in str(exc).lower():
        print("BLOCKED_AS_EXPECTED")
        sys.exit(0)
    raise
print("UNEXPECTEDLY_IMPORTED")
sys.exit(2)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"Expected plotly-blocked ImportError, got rc={result.returncode}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "BLOCKED_AS_EXPECTED" in result.stdout

    def test_mesh_handler_imports_plotly_at_module_level(self):
        """Documents why the transitive requirement exists: the import is
        module-level in core/mesh_handler (out of scope to fix here), so
        any caller of ``from core import ...`` drags plotly in."""
        import inspect

        import core.mesh_handler as mh

        source = inspect.getsource(mh)
        assert "import plotly" in source, (
            "core/mesh_handler ya no importa plotly en cabezera: revisar "
            "si Dockerfile-api aún necesita instalar plotly."
        )
