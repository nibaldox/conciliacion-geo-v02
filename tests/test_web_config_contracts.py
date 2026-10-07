"""Configuration contracts for the web deployment, CI gate and API base.

Stabilization unit C guards (see ``docs/WEB_STABILIZATION.md``):

* ``deploy-frontend.yml`` ships an absolute ``VITE_API_URL`` ending in
  ``/api/v1``; the portable/local workflows keep the relative ``/api/v1``;
  no workflow may duplicate the versioned prefix (``/api/v1/api/v1``).
* The web client resolves ``VITE_API_URL`` as-is (never re-appends the
  prefix) and the API routers stay mounted under ``/api/v1``.
* ``render.yaml`` declares only correctly prefixed ``CONCILIACION_*``
  variables, each read by ``core/config.py``; ``CONCILIACION_WORKERS``
  stays pinned to a single worker and matches the Docker runtime var.
* Import-time captures (``DEFAULTS.max_upload_mb``, ``api.main``'s
  ``_MAX_UPLOAD_BYTES``) reflect ``CONCILIACION_MAX_UPLOAD_MB`` in a fresh
  interpreter, with sane-range validation and a 500 MiB default preserved.
* ``ci.yml`` runs the real TS project typecheck, vitest with coverage over
  the complete suite — fullstack files included, with Python 3.12 + uv +
  ``uv.lock`` extras provisioned in the same job — and keeps the build.

The YAML files under test are only inspected through their ``KEY: value``
lines so no third-party YAML parser is required.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
PROBE_SCRIPT = Path(__file__).resolve().parent / "support" / "config_env_probe.py"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _workflow_vite_api_urls() -> dict[str, str]:
    urls: dict[str, str] = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*VITE_API_URL:\s*(.+?)\s*$", line)
            if match:
                urls[path.name] = match.group(1).strip("'\"")
    return urls


def _render_env_entries() -> dict[str, str]:
    entries: dict[str, str] = {}
    lines = _read("render.yaml").splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"\s*-\s*key:\s*(\S+)\s*$", line)
        if not match:
            continue
        for follow in lines[index + 1 : index + 3]:
            value_match = re.match(r"\s*value:\s*(.+?)\s*$", follow)
            if value_match:
                entries[match.group(1)] = value_match.group(1).strip("'\"")
                break
    return entries


def _probe(overrides: dict[str, str], with_api: bool = False) -> dict[str, object]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("CONCILIACION_")}
    env.update(overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, str(PROBE_SCRIPT)]
    if with_api:
        command.append("--with-api")
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"probe failed:\n{result.stdout}\n{result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestApiBaseContract:
    def test_deploy_frontend_url_is_absolute_versioned_and_unduplicated(self):
        value = _workflow_vite_api_urls()["deploy-frontend.yml"]
        assert value.startswith("https://"), (
            f"deploy-frontend.yml must build the Pages bundle with an absolute API root; got {value!r}"
        )
        assert value.endswith("/api/v1"), (
            "the deployed client concatenates relative paths (/meshes/...) onto VITE_API_URL "
            f"and never re-adds /api/v1; got {value!r}"
        )
        assert "/api/v1/api/v1" not in value

    def test_portable_and_local_workflows_keep_relative_versioned_base(self):
        urls = _workflow_vite_api_urls()
        for name in ("build.yml", "build-portable.yml", "release.yml"):
            assert urls[name] == "/api/v1", (
                f"{name} builds the local/portable bundle against the bundled sidecar; "
                f"expected VITE_API_URL=/api/v1, got {urls[name]!r}"
            )

    def test_no_workflow_duplicates_the_versioned_prefix(self):
        for name, value in _workflow_vite_api_urls().items():
            assert "/api/v1/api/v1" not in value, f"{name}: duplicated /api/v1 prefix"
            assert value.endswith("/api/v1"), f"{name}: VITE_API_URL must end in /api/v1"

    def test_deploy_url_composes_with_client_paths(self):
        base = _workflow_vite_api_urls()["deploy-frontend.yml"]
        hooks = _read("web/src/api/hooks.ts")
        assert re.search(r"client\.post\(\s*'/meshes/upload'", hooks), (
            "hooks.ts no longer posts to '/meshes/upload'; update this composition check"
        )
        composed = base.rstrip("/") + "/meshes/upload"
        assert composed.endswith("/api/v1/meshes/upload")
        assert composed.count("/api/v1") == 1

    def test_client_resolves_env_without_reappending_prefix(self):
        client_src = _read("web/src/api/client.ts")
        assert "const FALLBACK_API_BASE = '/api/v1'" in client_src
        assert "import.meta.env.VITE_API_URL" in client_src
        code = "\n".join(
            line
            for line in client_src.splitlines()
            if not line.strip().startswith(("//", "*", "/*"))
        )
        assert not re.search(r"\$\{[^}]*VITE_API_URL[^}]*\}\s*/api/v1", code), (
            "client.ts must not concatenate VITE_API_URL with /api/v1 in code"
        )

    def test_api_routers_stay_under_versioned_prefix(self):
        main_src = _read("api/main.py")
        include_lines = [line for line in main_src.splitlines() if "include_router(" in line]
        assert include_lines, "api/main.py no longer mounts routers via include_router"
        for line in include_lines:
            assert 'prefix="/api/v1"' in line, f"router not versioned: {line.strip()}"
        assert '@app.get("/api/v1/health")' in main_src


class TestRenderContract:
    def test_no_misspelled_conciliacion_prefix(self):
        entries = _render_env_entries()
        misspelled = sorted(key for key in entries if "CONCILIATION" in key)
        assert misspelled == [], (
            f"render.yaml declares misspelled env keys {misspelled}; core/config.py reads CONCILIACION_*"
        )

    def test_conciliacion_keys_are_read_by_core_config(self):
        declared = sorted(key for key in _render_env_entries() if key.startswith("CONCILIACION_"))
        assert declared, "render.yaml declares no CONCILIACION_* variables"
        core_src = _read("core/config.py")
        unread = [key for key in declared if f'"{key}"' not in core_src]
        assert unread == [], f"render.yaml declares {unread} but core/config.py never reads them"

    def test_workers_pinned_to_single_worker_and_matches_docker_runtime(self):
        entries = _render_env_entries()
        assert entries.get("CONCILIACION_WORKERS") == "1", (
            "CONCILIACION_WORKERS must stay 1: staging, in-memory caches/jobs and the local "
            "SQLite store are per-process (docs/WEB_STABILIZATION.md)"
        )
        assert "--workers $CONCILIACION_WORKERS" in _read("Dockerfile-api"), (
            "Dockerfile-api must consume the same var render.yaml declares"
        )

    def test_max_upload_mb_declared_value_matches_default(self):
        assert _render_env_entries().get("CONCILIACION_MAX_UPLOAD_MB") == "500"


class TestImportTimeConfigCaptures:
    def test_defaults_preserved_in_fresh_process(self):
        snapshot = _probe({})
        assert snapshot["max_upload_mb"] == 500
        assert snapshot["workers"] == 1
        assert snapshot["log_format"] == "plain"

    def test_max_upload_mb_env_value_is_effective(self):
        snapshot = _probe({"CONCILIACION_MAX_UPLOAD_MB": "250"})
        assert snapshot["max_upload_mb"] == 250

    @pytest.mark.parametrize("raw", ["abc", "0", "-5", "12.5", "99999999"])
    def test_insane_max_upload_values_fall_back_to_500(self, raw):
        snapshot = _probe({"CONCILIACION_MAX_UPLOAD_MB": raw})
        assert snapshot["max_upload_mb"] == 500

    def test_log_format_env_value_is_effective(self):
        snapshot = _probe({"CONCILIACION_LOG_FORMAT": "json"})
        assert snapshot["log_format"] == "json"

    def test_api_import_captures_effective_limit(self, tmp_path):
        snapshot = _probe(
            {
                "CONCILIACION_MAX_UPLOAD_MB": "250",
                "CONCILIACION_DATA_DIR": str(tmp_path),
            },
            with_api=True,
        )
        assert snapshot["api_max_upload_bytes"] == 250 * 1024 * 1024

    def test_api_import_default_limit(self, tmp_path):
        snapshot = _probe({"CONCILIACION_DATA_DIR": str(tmp_path)}, with_api=True)
        assert snapshot["api_max_upload_bytes"] == 500 * 1024 * 1024


def _ci_job_block(job: str) -> str:
    lines = _read(".github/workflows/ci.yml").splitlines()
    start = next(
        (index for index, line in enumerate(lines) if re.match(rf"^  {re.escape(job)}:\s*$", line)),
        None,
    )
    assert start is not None, f"ci.yml has no {job!r} job"
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^  \S+:\s*$", lines[index])
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


class TestCiGate:
    def test_ci_runs_real_typecheck_tests_with_coverage_and_build(self):
        ci = _read(".github/workflows/ci.yml")
        assert re.search(r'node-version:\s*"?22"?', ci), "CI frontend job must stay on Node 22"
        assert "npx tsc -b" in ci, (
            "CI must run the referenced-project typecheck (tsc -b); plain `tsc --noEmit` "
            "on the solution tsconfig checks nothing"
        )
        assert "npx tsc --noEmit" not in ci
        assert "npm run lint" in ci
        assert "npm run test:coverage" in ci
        assert "npm run build" in ci

    def test_ci_frontend_runs_complete_suite_without_exclusions(self):
        block = _ci_job_block("frontend-build")
        assert "--exclude" not in block, (
            "the CI frontend gate must run the complete vitest suite; excluding "
            "files violates the stabilization acceptance"
        )
        assert "--skip" not in block and "skipFiles" not in block, (
            "no skip flag may hide frontend tests in CI"
        )
        run_lines = [
            line.strip() for line in block.splitlines() if "npm run test:coverage" in line
        ]
        assert run_lines, "the frontend job no longer runs npm run test:coverage"
        assert any(re.fullmatch(r"run:\s*npm run test:coverage", line) for line in run_lines), (
            f"the coverage gate must be the bare suite command; got {run_lines}"
        )
        for name in (
            "web/tests/blast.fullstack.test.tsx",
            "web/tests/blast.fullstack.hermeticity.test.tsx",
        ):
            assert "runIntegrationHarness" in _read(name), f"{name} must drive the real harness"

    def test_ci_frontend_job_provisions_python_uv_and_locked_deps(self):
        block = _ci_job_block("frontend-build")
        assert re.search(r'python-version:\s*"3\.12"', block), (
            "the frontend job must provision Python 3.12 for the uv harness"
        )
        assert re.search(r"uses:\s*astral-sh/setup-uv@", block), (
            "the frontend job must install uv (GitHub runners do not ship it)"
        )
        sync_lines = [
            line.strip()
            for line in block.splitlines()
            if re.match(r"run:\s*uv sync\b", line.strip())
        ]
        assert sync_lines, "the frontend job must provision the uv project environment"
        command = sync_lines[0]
        assert "--locked" in command or "--frozen" in command, (
            f"uv provisioning must honor the committed uv.lock; got {command!r}"
        )
        assert "--extra test" in command, (
            f"provisioning must install the real [test] extra that backs the harness; got {command!r}"
        )
        assert "--python 3.12" in command, f"provisioning must pin Python 3.12; got {command!r}"
        assert (REPO_ROOT / "uv.lock").is_file(), (
            "uv.lock must be committed: CI provisions from the locked manifest"
        )
        assert block.index("uv sync") < block.index("npm run test:coverage"), (
            "harness prerequisites must be provisioned in the same job before the suite runs"
        )

    def test_ci_frontend_freezes_uv_sync_for_the_harness_subprocess(self):
        block = _ci_job_block("frontend-build")
        suite_step = block[block.index("Run unit tests with coverage") : block.index("npm run build")]
        assert re.search(r'UV_NO_SYNC:\s*"?1"?', suite_step), (
            "the coverage step must export UV_NO_SYNC=1: integrationHarness spawns "
            "`uv run python` and an implicit sync would re-resolve the environment "
            "without the [test] extra and could drop harness deps"
        )
        harness = _read("web/tests/support/integrationHarness.ts")
        assert "'uv'" in harness
        assert "'run', 'python'" in harness, "integrationHarness must spawn `uv run python`"
        assert "{ ...process.env }" in harness, (
            "integrationHarness must keep spreading process.env so the step env reaches `uv run`"
        )

    def test_stabilization_doc_reflects_full_ci_prerequisites(self):
        doc = _read("docs/WEB_STABILIZATION.md")
        assert "--exclude" not in doc, "the stabilization doc must not keep the removed exclusion"
        assert "uv.lock" in doc, "the doc must describe lockfile-driven provisioning"
        assert "UV_NO_SYNC" in doc, "the doc must document the sync-freeze prerequisite"
        assert "3.12" in doc, "the doc must document the pinned Python 3.12 prerequisite"

    def test_deploy_workflow_typecheck_is_real(self):
        deploy = _read(".github/workflows/deploy-frontend.yml")
        assert "npx tsc -b" in deploy
        assert "npx tsc --noEmit" not in deploy

    def test_package_scripts_back_the_ci_commands(self):
        pkg = json.loads(_read("web/package.json"))
        assert "vitest" in pkg["scripts"]["test:coverage"]
        assert "tsc -b" in pkg["scripts"]["build"]
        assert "@vitest/coverage-v8" in pkg["devDependencies"]

    def test_deploy_build_receives_only_public_values(self):
        deploy = _read(".github/workflows/deploy-frontend.yml")
        keys = set(re.findall(r"^\s+([A-Z][A-Z0-9_]*):", deploy, re.M))
        allowed = {
            "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24",
            "VITE_BASE",
            "VITE_API_URL",
            "VITE_SENTRY_DSN",
            "VITE_ANALYTICS_URL",
            "VITE_RELEASE",
        }
        unexpected = sorted(keys - allowed)
        assert unexpected == [], (
            f"deploy-frontend.yml passes unexpected keys {unexpected}; the Pages bundle "
            "must only receive public VITE_* build values"
        )

    def test_ci_gate_consumes_no_repository_secrets(self):
        assert "secrets." not in _read(".github/workflows/ci.yml")
