# Testing Capabilities — conciliacion-geo-v02

**Strict TDD Mode**: disabled
**Detected**: 2026-07-10
**Rationale**: test-after workflow per CONTRIBUTING.md; domain layer uses 100% vitest coverage as TDD surrogate.

---

## Backend — pytest

- **Runner command**: `pytest tests/ -v --tb=short`
- **Framework**: pytest (managed via `pyproject.toml` `[tool.pytest.ini_options]`)
- **Test root**: `tests/`
- **pythonpath**: `.` (root)
- **Excluded**: `tests/test_openblast.py` when the optional `openblast` package is not installed
- **Pipeline smoke**: `python test_pipeline.py` — runs the synthetic end-to-end pipeline (mesh → sections → params → Excel/Word export)
- **Coverage**: not enforced at CI. `.coverage` file present locally (pytest-cov installed locally via dev tooling).

### Layers

| Layer | Available | Tool |
|---|---|---|
| Unit | yes | pytest |
| Integration | yes | httpx + FastAPI TestClient (`tests/test_api.py`, `tests/test_api_auth.py`, `tests/test_api_static_mount.py`) |
| E2E (pipeline) | yes | `python test_pipeline.py` (synthetic STL/DXF) |

### Test inventory (representative)

- `test_param_extractor.py` (60 KB — large bench-detection regression suite)
- `test_blast_correlation.py`, `test_blast_integration.py`, `test_blast_metrics.py` (drill & blast)
- `test_section_cutter.py`, `test_mesh_handler.py`, `test_mesh_validation.py` (mesh pipeline)
- `test_api.py`, `test_ai_router.py`, `test_ai_v2_*` (API surface)
- `test_stability_analysis.py`, `test_alert_system.py`, `test_compliance_status.py` (analytical modules)
- `test_report_generator.py`, `test_excel_writer.py` (export)

Total collected: ~772 tests (per AGENTS.md; README badge is stale).

### System dep

- `libspatialindex-dev` (apt) / `spatialindex` (brew) — required for `rtree` / AABB operations on large meshes.

---

## Frontend — vitest + Playwright

- **Runner command**: `npm run test`
- **Framework**: vitest 4.1.8 + @testing-library/react 16.3 + jsdom
- **Config**: `web/vite.config.ts` `test:` block (jsdom env, globals true, setupFiles `src/test/setup.ts`)
- **Watch mode**: `npm run test:watch`
- **Coverage scope**: `src/components/results/ProfileView/domain/**` only
- **Coverage thresholds**: 100% statements / branches / functions / lines (`npm run test:domain`)

### Layers

| Layer | Available | Tool |
|---|---|---|
| Unit (domain) | yes | vitest (`src/components/results/ProfileView/domain/__tests__/*.test.ts`) |
| Component | yes | @testing-library/react (`src/test/setup.ts` includes `@testing-library/jest-dom/vitest`) |
| E2E | yes | @playwright/test 1.59 (chromium, `web/e2e/*.spec.ts`) |

### E2E prerequisites (Playwright `playwright.config.ts`)

The `webServer` block auto-starts:
- API: `uvicorn api.main:app --port 8000` (cwd: repo root)
- Web: `npm run dev` (cwd: web)

Both ports (8000 + 5173) must be reachable. `reuseExistingServer: true` allows local debug without restart.

### Domain test files (100% coverage gate)

```
src/components/results/ProfileView/domain/__tests__/
├── compliance.test.ts
├── filters.test.ts
├── sorting.test.ts
├── status.test.ts
├── mapping.test.ts
└── mapping.legacyReconciled.test.ts
```

---

## Quality Tools

| Tool | Available | Command |
|---|---|---|
| Python linter | no | — |
| Python formatter | no | — |
| Python type checker | no | — |
| TS type checker | yes | `npx tsc --noEmit` (CI: `web` cwd) |
| TS linter | **broken** | `npm run lint` → `eslint .` (no eslint dep, no config file) |
| CSS formatter | implicit | Tailwind 4 via `@tailwindcss/vite` |
| Pre-commit hooks | none | — |

---

## Recommended Verification Stack (for SDD `verify`)

```bash
# Backend
pytest tests/ -v --tb=short
python test_pipeline.py

# Frontend
cd web && npm run build         # tsc -b && vite build
cd web && npm run test          # vitest run
cd web && npm run test:domain   # scoped to ProfileView/domain (coverage gate)
cd web && npx tsc --noEmit      # typecheck only

# Optional E2E (requires API + web running)
cd web && npm run test:e2e
```

CI (`.github/workflows/ci.yml`) runs **only**: `pytest tests/` + `python test_pipeline.py` + `npm run build` + `npx tsc --noEmit` + docker-compose smoke. **Frontend vitest and playwright are local-only** — CI does not enforce them.