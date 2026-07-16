# SDD Init Report — conciliacion-geo-v02

**Detected**: 2026-07-10
**Persistence mode**: openspec (file-based)
**Strict TDD**: disabled
**Status**: ok (1 risk noted)

## Executive Summary

Geotechnical reconciliation platform for open-pit mine slopes. Python 3.10+ backend (`core/` shared domain, `api/` FastAPI, `app.py` legacy Streamlit) paired with React 19 + Vite 6 + TypeScript frontend (`web/`). Package management uses uv (uv.lock present) on the backend and npm on the frontend. Test infrastructure is solid on both sides (pytest + vitest + Playwright); 100% coverage is enforced only on the ProfileView domain layer as a TDD surrogate. One operational risk: `npm run lint` references ESLint but neither the dependency nor a config file exists in the repo.

## Repo Facts

| Fact | Value | Source |
|---|---|---|
| Python constraint | `>=3.10` | `pyproject.toml` (`requires-python`) |
| Python (CI) | 3.12 | `.github/workflows/ci.yml` |
| Python (local) | 3.14.6 | `python -c "import sys"` |
| Build backend | setuptools >=68.0 | `pyproject.toml` |
| Package manager (backend) | uv (uv.lock 645 KB present) | repo root |
| Package manager (frontend) | npm (package-lock.json 496 KB) | `web/package-lock.json` |
| Frontend framework | React 19.1 + Vite 6.3 + TypeScript ~5.8 | `web/package.json`, `web/tsconfig.app.json` |
| 3D viewer | CesiumJS (pre-bundled in `web/public/Cesium/`, NOT in package.json) | `AGENTS.md` |
| Charts | Plotly 2.35 + Chart.js 4.5 | `web/package.json` |
| State | Zustand 5 + TanStack Query/Table | `web/package.json` |
| i18n | i18next + ICU plurals | `web/package.json`, CONTRIBUTING.md |
| Backend web framework | FastAPI (mounted under `/api/v1`) | `api/main.py`, AGENTS.md |
| Optional backend dep | `openblast` (skip `tests/test_openblast.py` if missing) | `tests/test_openblast.py`, AGENTS.md |
| System deps | `libspatialindex-dev` (apt) / `spatialindex` (brew) | `AGENTS.md`, CI |
| Python version pin | None (CI pins 3.12 only) | `.github/workflows/ci.yml` |
| Python formatter | none configured | — |
| Python linter | none configured | — |
| Python type checker | none configured | — |
| TS linter | declared (`npm run lint` → `eslint .`) but **BROKEN** | `web/package.json` |
| TS type checker | `npx tsc --noEmit` | CI, AGENTS.md |
| TS config | strict + noUnusedLocals + noUnusedParameters | `web/tsconfig.app.json` |
| Pre-commit hooks | none | — |

## Off-limits (do not modify)

- `app.py` — Streamlit legacy UI, used daily by maintainer.
- `ui/` — Streamlit legacy UI directory.
- `cli.py` — Production legacy CLI.
- `core/__init__.py` — Re-exports legacy stable public API. Additive changes inside `core/` submodules are welcome.

## Directories Created

```
openspec/
├── config.yaml                              # SDD config + testing capabilities
├── specs/                                   # (empty — main spec source-of-truth)
├── changes/
│   └── archive/                             # (empty — completed changes go here)
└── sdd-init/
    └── conciliacion-geo-v02/
        └── init-report.md                   # this file
```

## Testing Capabilities (cached)

### Backend — pytest

- **Command**: `pytest tests/ -v --tb=short`
- **Framework**: pytest 8.x via pyproject.toml `[tool.pytest.ini_options]`
- **pythonpath**: `.` (so `from core import ...` works)
- **Collected**: ~772 tests (per AGENTS.md; CONTRIBUTING.md cites stale "97 tests")
- **Exclude**: `tests/test_openblast.py` when `openblast` package is not installed
- **Pipeline smoke**: `python test_pipeline.py` (synthetic STL→sections→params→export)
- **Coverage**: not enforced; `.coverage` file present locally (pytest-cov installed locally)

| Layer | Available | Tool |
|---|---|---|
| Unit | ✅ | pytest |
| Integration | ✅ | httpx + FastAPI TestClient |
| E2E (pipeline) | ✅ | python test_pipeline.py |

### Frontend — vitest + Playwright

- **Command**: `npm run test`
- **Framework**: vitest 4.1.8 + @testing-library/react + jsdom
- **Coverage**: `@vitest/coverage-v8` with `src/components/results/ProfileView/domain/**` scoped
- **100% thresholds**: statements / branches / functions / lines
- **Domain test files**: `__tests__/compliance.test.ts`, `filters.test.ts`, `sorting.test.ts`, `status.test.ts`, `mapping.test.ts`, `mapping.legacyReconciled.test.ts`
- **E2E**: Playwright config (`playwright.config.ts`) auto-starts API :8000 + web :5173 via `webServer` blocks

| Layer | Available | Tool |
|---|---|---|
| Unit | ✅ | vitest |
| Component | ✅ | @testing-library/react |
| E2E | ✅ | @playwright/test |

### Quality Tools

| Tool | Available | Command |
|---|---|---|
| Python linter | ❌ | — |
| Python formatter | ❌ | — |
| Python type checker | ❌ | — |
| TS type checker | ✅ | `npx tsc --noEmit` |
| TS linter | ⚠️ broken | `npm run lint` → `eslint .` (no eslint dep, no config) |
| CSS formatter | implicit | Tailwind 4 (no separate formatter) |

## Strict TDD Resolution

**Decision**: `strict_tdd: false`

**Reasoning**:
- No pre-commit hook enforcing test-first ordering.
- No `tests/test_first.md` or RED-GREEN-REFACTOR markers in the repo.
- CONTRIBUTING.md describes a standard test-after flow: "If your PR adds a new public function, **add a test** for it."
- Domain layer enforces 100% coverage via vitest (`npm run test:domain`) — this is the project's TDD surrogate.
- CI does not run vitest or playwright (per AGENTS.md), so strict TDD would have no enforcement point at the gate level.

The orchestrator confirmed this default. SDD `apply` will follow standard test-after with `[ ] write test → [ ] implement → [ ] run tests` task ordering, but ordering is **advisory**, not blocking.

## Detection Artifacts

- `.atl/skill-registry.md` — already exists (auto-generated 2026-07-10, 154 lines). Not regenerated.
- `.atl/.skill-registry.cache.json` — already exists. Not touched.

## Skill Registry

Existing registry at `.atl/skill-registry.md` covers:
- `~/.agents/skills/`
- `~/.config/opencode/skills/`
- `~/.openclaw/skills/`
- `~/.hermes/skills/`

Last updated 2026-07-10. Refresh is outside the scope of `sdd-init`; the orchestrator can invoke `skill-registry` separately if it needs a refresh.

## Risks

1. **`npm run lint` is broken**: ESLint is not in `devDependencies` and no config file (`.eslintrc*`, `eslint.config.js`) exists. Running `npm run lint` will fail. Either the maintainer runs ESLint globally or the script is dead. Worth flagging to the maintainer — fix by either installing `eslint` + flat config, or removing the script.
2. **Test count drift**: CONTRIBUTING.md says "97 tests" but AGENTS.md says "~772". The 633/633 badge in README.md is stale. Detection should not be considered authoritative for a single source-of-truth count.
3. **No Python linter/formatter**: PEP 8 enforcement is by convention only. PRs may drift.
4. **CI does not run frontend tests**: vitest + playwright are local-only. UI regressions can land to main if contributors skip the local run.
5. **Domain 100% coverage is a single-file guard**: only `web/src/components/results/ProfileView/domain/**` is gated. Other layers can drop to 0% without breaking CI.

## Next Recommended Step

`sdd-explore` — when the user has a concrete change idea. Or `sdd-new` to scaffold a change directly.

No change is queued. Once the user invokes `/sdd-explore` or `/sdd-new`, the orchestrator will create `openspec/changes/{change-name}/` and continue the cycle.