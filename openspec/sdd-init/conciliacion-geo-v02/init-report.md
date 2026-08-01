# SDD Init Report — conciliacion-geo-v02

**Detected**: 2026-07-30 (refresh of 2026-07-10 baseline)
**Persistence mode**: hybrid (engram + filesystem)
**Strict TDD**: disabled
**Status**: ok

## Executive Summary

Geotechnical reconciliation platform for open-pit mine slopes — Python 3.10+ backend (`core/` shared domain, `api/` FastAPI, `app.py` legacy Streamlit) paired with React 19 + Vite 6 + TypeScript frontend (`web/`). Package management: uv on the backend (uv.lock present, setuptools build via pyproject.toml) and npm on the frontend. Test infrastructure is solid on both sides (pytest + vitest + Playwright); 100% coverage is enforced only on the ProfileView domain layer as a TDD surrogate. One operational risk remains: `npm run lint` references ESLint but neither the dependency nor a config file exists in the repo.

This phase was re-executed in HYBRID mode (filesystem + Engram), with `auto_execution: true`, `delivery_strategy: auto-chain`, and `chain_strategy: feature-branch-chain` recorded in `openspec/config.yaml` under `artifact_store`. Existing specs/changes were preserved — only the bootstrap metadata and this report were refreshed.

## Repo Facts

| Fact | Value | Source |
|---|---|---|
| Python constraint | `>=3.10` | `pyproject.toml` (`requires-python`) |
| Python (CI) | 3.12 | `.github/workflows/ci.yml` |
| Build backend | setuptools >=68.0 | `pyproject.toml` |
| Package manager (backend) | uv (uv.lock present) | repo root |
| Package manager (frontend) | npm (package-lock.json) | `web/package-lock.json` |
| Frontend framework | React 19.1 + Vite 6.3 + TypeScript ~5.8 | `web/package.json`, `web/tsconfig.app.json` |
| 3D viewer | CesiumJS (pre-bundled in `web/public/Cesium/`, NOT in package.json) | `AGENTS.md` |
| Charts | Plotly 2.35 + Chart.js 4.5 | `web/package.json` |
| State | Zustand 5 + TanStack Query/Table | `web/package.json` |
| i18n | i18next + ICU plurals | `web/package.json`, `CONTRIBUTING.md` |
| Backend web framework | FastAPI (mounted under `/api/v1`) | `api/main.py`, `AGENTS.md` |
| Optional backend dep | `openblast` (skip `tests/test_openblast.py` if missing) | `tests/test_openblast.py`, `AGENTS.md` |
| System deps | `libspatialindex-dev` (apt) / `spatialindex` (brew) | `AGENTS.md`, `ci.yml` |
| Python formatter | none configured | — |
| Python linter | none configured | — |
| Python type checker | none configured | — |
| TS linter | declared (`npm run lint` → `eslint .`) but **BROKEN** | `web/package.json` |
| TS type checker | `npx tsc --noEmit` | CI, `AGENTS.md` |
| TS config | strict + noUnusedLocals + noUnusedParameters | `web/tsconfig.app.json` |
| Pre-commit hooks | none | — |
| Artifact store mode | hybrid (engram + filesystem) | `openspec/config.yaml` |

## Off-limits (do not modify)

- `app.py` — Streamlit legacy UI, used daily by maintainer.
- `ui/` — Streamlit legacy UI directory.
- `cli.py` — Production legacy CLI.
- `core/__init__.py` — Re-exports legacy stable public API. Additive changes inside `core/` submodules are welcome.

## Persistence Mode (Hybrid)

The orchestrator passed `artifact_store.mode = hybrid`. Per `persistence-contract.md`:

- **Reads**: Engram first (cross-session recovery), filesystem fallback.
- **Writes**: BOTH must succeed — Engram `mem_save` AND filesystem write per artifact.
- **Cost note**: hybrid consumes more tokens per operation. Use only when you need both cross-session persistence AND local file artifacts. Trade-off accepted for this project because specs/changes live in git and need Engram for compaction survival during long /sdd-* sessions.

Engram keys used by this init phase (topic_key → title → type):

| topic_key | title | type | project | scope |
|---|---|---|---|---|
| `sdd-init/conciliacion-geo-v02` | `sdd-init/conciliacion-geo-v02` | `architecture` | `conciliacion-geo-v02` | `project` |
| `sdd/conciliacion-geo-v02/testing-capabilities` | `sdd/conciliacion-geo-v02/testing-capabilities` | `config` | `conciliacion-geo-v02` | `project` |
| `skill-registry` | `skill-registry` | `config` | `conciliacion-geo-v02` | `project` |

All three were saved with `capture_prompt: false` (automated SDD pipeline output). Subsequent `/sdd-*` phases should upsert on the same `topic_key` per `engram-convention.md`.

## Directories Created / Refreshed

```
openspec/
├── config.yaml                              # SDD config + artifact_store + testing capabilities (REFRESHED 2026-07-30)
├── specs/                                   # source-of-truth main specs (8 domains; preserved)
│   ├── blast-backbreak-prediction/spec.md
│   ├── blast-design-achievement/spec.md
│   ├── blast-drill-compliance/spec.md
│   ├── blast-hole-attribution/spec.md
│   ├── blast-multivariate-correlation/spec.md
│   ├── drill-hardness-integration/spec.md
│   ├── reconciled-profile-serialization/spec.md
│   └── streamlit-legacy-surface-integrity/spec.md
├── changes/                                 # active + archive (preserved)
│   ├── ACTIVE.md                            # no in-flight changes
│   ├── archive/                             # 8 completed changes
│   └── streamlit-audit-remediation/         # historical artefact (tasks.md only)
└── sdd-init/
    └── conciliacion-geo-v02/
        └── init-report.md                   # this file (REFRESHED 2026-07-30)

.atl/
├── skill-registry.md                        # REFRESHED 2026-07-30 (auto-regenerated)
└── .skill-registry.cache.json               # regenerated fingerprint

.gitignore                                   # .atl/ already ignored (line 41)
```

## Testing Capabilities

### Backend — pytest

- **Command**: `pytest tests/ -v --tb=short`
- **Framework**: pytest 8.x via `pyproject.toml` `[tool.pytest.ini_options]`
- **pythonpath**: `.` (so `from core import ...` works)
- **Collected**: ~772 tests (per `AGENTS.md`; `CONTRIBUTING.md` cites stale "97 tests")
- **Exclude**: `tests/test_openblast.py` when `openblast` package is not installed
- **Pipeline smoke**: `python test_pipeline.py` (synthetic STL→sections→params→export)
- **Coverage**: not enforced at the gate; `.coverage` file present locally (pytest-cov installed locally)

| Layer | Available | Tool |
|---|---|---|
| Unit | ✅ | pytest |
| Integration | ✅ | httpx + FastAPI TestClient (`tests/api/conftest.py`) |
| E2E (pipeline) | ✅ | `python test_pipeline.py` |

### Frontend — vitest + Playwright

- **Command**: `npm run test`
- **Framework**: vitest 4.1.8 + `@testing-library/react` + jsdom
- **Coverage**: `@vitest/coverage-v8` with `src/components/results/ProfileView/domain/**` scoped
- **100% thresholds**: statements / branches / functions / lines
- **Domain test files**: `__tests__/compliance.test.ts`, `filters.test.ts`, `sorting.test.ts`, `status.test.ts`, `mapping.test.ts`, `mapping.legacyReconciled.test.ts`
- **E2E**: Playwright config (`playwright.config.ts`) auto-starts API :8000 + web :5173 via `webServer` blocks

| Layer | Available | Tool |
|---|---|---|
| Unit | ✅ | vitest |
| Component | ✅ | `@testing-library/react` |
| E2E | ✅ | `@playwright/test` |

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
- `CONTRIBUTING.md` describes a standard test-after flow: "If your PR adds a new public function, **add a test** for it."
- Domain layer enforces 100% coverage via vitest (`npm run test:domain`) — this is the project's TDD surrogate.
- CI does not run vitest or playwright (per `AGENTS.md`), so strict TDD would have no enforcement point at the gate level.

SDD `apply` follows standard test-after with `[ ] write test → [ ] implement → [ ] run tests` task ordering, but ordering is **advisory**, not blocking.

## Skill Registry

Registry at `.atl/skill-registry.md` was regenerated this session (sources scanned: `/home/xodla/.hermes/skills`, `/home/xodla/.agents/skills`, `/home/xodla/.config/opencode/skills`, `/home/xodla/.claude/skills`; `sdd-*`, `_shared`, and `skill-registry` skipped per skill-registry convention). `.atl/.skill-registry.cache.json` fingerprint updated.

## Risks

1. **`npm run lint` is broken**: ESLint is not in `devDependencies` and no config file exists. Running `npm run lint` will fail. Either the maintainer runs ESLint globally or the script is dead. Worth flagging to the maintainer — fix by either installing `eslint` + flat config, or removing the script.
2. **Test count drift**: `CONTRIBUTING.md` says "97 tests" but `AGENTS.md` says "~772". The 633/633 badge in `README.md` is stale. Detection should not be considered authoritative for a single source-of-truth count.
3. **No Python linter/formatter**: PEP 8 enforcement is by convention only. PRs may drift.
4. **CI does not run frontend tests**: vitest + playwright are local-only. UI regressions can land to main if contributors skip the local run.
5. **Domain 100% coverage is a single-file guard**: only `web/src/components/results/ProfileView/domain/**` is gated. Other layers can drop to 0% without breaking CI.
6. **Hybrid token cost**: writing every artifact twice (Engram + filesystem) increases orchestrator token usage. Acceptable for this project because long /sdd-* sessions benefit from compaction survival.

## Next Recommended Step

`sdd-explore` — when the user has a concrete change idea. Or `sdd-new` to scaffold a change directly via the `auto-chain` delivery strategy.

No change is queued. `openspec/changes/ACTIVE.md` is empty. Once the user invokes `/sdd-explore` or `/sdd-new`, the orchestrator will create `openspec/changes/{change-name}/` and continue the cycle.