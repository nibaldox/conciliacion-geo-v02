"""Import-order regression tests for the handlers <-> api.routers cycle.

``api/routers/__init__.py`` imports ``ai`` at package init and
``ai.py`` imports ``api.ai_agent_handlers``, so a module-level import of
``api.routers.process`` inside the handlers module breaks when it is
imported first (solo pytest collection). Fresh subprocess imports pin
the deferred-import fix regardless of collection order.
"""
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_TIMEOUT_S = 120


class TestAiAgentHandlersImportOrder:
    def test_handlers_module_imports_solo(self):
        code = "import api.ai_agent_handlers; print('OK')"
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=_TIMEOUT_S,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_handlers_modules_import_together(self):
        code = "import api.ai_agent_handlers, api.ai_agent_write_handlers; print('OK')"
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=_TIMEOUT_S,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_routers_first_then_handlers(self):
        code = "import api.routers.process; import api.ai_agent_handlers; print('OK')"
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=_TIMEOUT_S,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout
