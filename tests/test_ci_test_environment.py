"""Regression guard for the hermetic backend-test environment (V6 CI repair).

The backend suite depends on the ``test`` extra declared in ``pyproject.toml``:
pytest-asyncio (the async tests in ``tests/test_ai_v2_*.py``) and httpx
(FastAPI's ``TestClient``). Both CI workflows install it via
``pip install -e ".[test]"``.

If a workflow is misconfigured and the extra is absent, the imports below fail
at collection time with a clear ``ModuleNotFoundError`` — instead of the cryptic
``Unknown pytest.mark.asyncio`` that masked the root cause in PR #25. The test
then additionally asserts the asyncio plugin is *active*, not just importable.
"""
from __future__ import annotations

import httpx
import pytest_asyncio


def test_pytest_asyncio_plugin_is_active(pytestconfig):
    assert pytestconfig.pluginmanager.has_plugin("asyncio"), (
        "pytest-asyncio is importable but not loaded as a plugin; the async "
        "tests in tests/test_ai_v2_*.py would fail with 'Unknown pytest.mark."
        "asyncio'. Reinstall the test extra: pip install -e .[test]"
    )
