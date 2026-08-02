"""Smoke import tests — the backend must import on Python 3.10+ (audit H-01).

Fixes the NameError that surfaced on Python 3.12 (annotations evaluated
eagerly there; Python 3.14 defers them via PEP 649, masking the bug):
``Optional`` was used in core.config without importing it.
"""
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestImportSmoke:
    def test_core_config_imports(self):
        import core.config  # noqa: F401

    def test_core_package_imports(self):
        import core  # noqa: F401
        from core import load_mesh  # noqa: F401
        from core.config import EXPLOSIVE

        assert EXPLOSIVE.energy_mj_per_kg("ANFO") == 3.72

    def test_explosive_properties_imports(self):
        import core.explosive_properties  # noqa: F401

    def test_backend_imports_in_fresh_interpreter(self):
        """The whole backend must import in a clean subprocess (like CI)."""
        code = "import api.main; import core; import core.config; print('OK')"
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_api_imports_without_reportlab(self):
        """Fase 1.1 cierre §3: the API must import even when reportlab is
        missing (the PDF report is a localised dependency with a clear error)."""
        code = """
import sys

class _BlockReportlab:
    def find_module(self, name, path=None):
        if name == "reportlab" or name.startswith("reportlab."):
            raise ImportError("blocked for test")

sys.meta_path.insert(0, _BlockReportlab())
import api.main  # must NOT raise
print("API_OK")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert "API_OK" in result.stdout
