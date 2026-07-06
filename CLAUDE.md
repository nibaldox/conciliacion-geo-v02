# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Geotechnical reconciliation for open-pit mine slopes. Compares 3D **design** vs **as-built** surfaces (STL/OBJ/DXF), cuts cross-sections, extracts bench parameters (height, face angle, berm width), and evaluates compliance against tolerances → **CUMPLE / FUERA DE TOLERANCIA / NO CUMPLE**.

**User**: geotechnical engineer in LatAm open-pit mining (Vulkan, Campbell CR300, IBIS radar, vibrating-wire piezometers). UI is Spanish; communicates in Spanish.

**Stack**: Python 3.10+, trimesh, fast_simplification, numpy/scipy/shapely, FastAPI, Streamlit, openpyxl, python-docx, ezdxf, openai. Web: React 19, Vite 6, TypeScript, Tailwind 4, CesiumJS, Plotly, Zustand, TanStack Query/Table, i18next.

> `AGENTS.md` is a more exhaustive quick-reference (commands + pitfalls). `docs/` holds the deep architecture/audit docs. This file is the Claude Code operating summary — defer to those for detail.

## Commands

```bash
# --- Setup ---
# System dep required: libspatialindex-dev (apt) / spatialindex (brew) — rtree needs it
pip install -e .                    # editable install (pyproject.toml); or: uv sync
pip install -r requirements-api.txt # API-only deps
cd web && npm ci                    # frontend deps

# --- Dev (API + web together; Ctrl+C stops both) ---
bash dev.sh
#   → API on http://localhost:8000/docs  (Vite picks its own port, printed by dev.sh)

# --- Run subsystems individually ---
uvicorn api.main:app --reload --port 8000   # FastAPI backend
cd web && npm run dev                       # React dev server (proxies /api → :8000)
streamlit run app.py                        # ⚠️ LEGACY UI — DO NOT MODIFY (see below)
python cli.py --design diseno.stl --topo topo.stl --auto \
  --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0 --length 200
python cli.py --design diseno.stl --topo topo.stl --config ejemplo_secciones.json

# --- Python tests (pytest, pythonpath="." per pyproject.toml) ---
pytest tests/ -v --tb=short                                              # full suite (~114; count shifts)
pytest tests/test_param_extractor.py                                     # one file
pytest tests/test_param_extractor.py::TestParamExtractor::test_extract_parameters -v  # one test
python test_pipeline.py                                                  # synthetic end-to-end

# --- Web tests / quality (CI does NOT run these — run locally before pushing UI) ---
cd web && npm run test            # vitest (100% coverage enforced on ProfileView/domain/** only)
cd web && npm run test:e2e        # playwright (needs API + web running)
cd web && npm run lint            # ESLint
cd web && npx tsc --noEmit        # typecheck
cd web && npm run build           # production build (PWA on)
VITE_PWA=false npm run build      # build without service worker (Electron bundle requires this)

# --- Docker / deploy ---
docker build -f Dockerfile-api  -t conciliacion-api  .
docker build -f Dockerfile-web  -t conciliacion-web  .
docker-compose up
# Electron portable bundle: first `pyinstaller conciliacion-api.spec`, then electron-builder in electron/
```

No Python linter/formatter is configured. Web has ESLint + TypeScript strict.

## Architecture

Three interfaces share one domain engine (`core/`). The engine is the source of truth; interfaces are thin.

```
                         ┌─────────────────────────────┐
   STL/OBJ/DXF input ──▶ │  core/  (domain engine)      │
                         └──────────────┬───────────────┘
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
   Streamlit (app.py+ui/)      FastAPI (api/)              cli.py
   LEGACY, OFF-LIMITS          wraps core, SQLite session  wraps core, file exports
   imports core directly       ▲
                                │  /api/v1/*  (X-Session-ID header)
                                │
                          React web/  ◀── active development
                                │
                          Electron  (portable bundle: PyInstaller sidecar + web build)
```

### Core pipeline (`core/`)

1. `load_mesh(path)` → `trimesh.Trimesh` (supports STL/OBJ/PLY/DXF; optional decimation)
2. `cut_mesh_with_section(mesh, section)` → `ProfileResult` (distances, elevations)
3. `extract_parameters(distances, elevations)` → `ExtractionResult`: RDP simplify → local-angle classification (face ≥40°, berm ≤20°) → bench merge → **Hungarian-matched** design-vs-as-built
4. `compare_design_vs_asbuilt(...)` → three-tier compliance (**CUMPLE** within tol → **FUERA** ≤1.5× tol → **NO CUMPLE** >1.5× tol)
5. `export_results` / `generate_word_report` / `generate_section_images_zip` → Excel (Resumen, Bancos, Inter-Rampa, Dashboard, Rampas) / Word / DXF / PNG zip

Key modules: `mesh_handler`, `section_cutter`, `param_extractor` (orchestrator + dataclasses), `profile_extract` / `profile_simplify` / `bench_classify` / `profile_compliance` (the reconciliation sub-pipeline), `excel_writer`, `report_generator`, `calculo_tronadura` + `blast_*` (drill & blast), `breaklines`, `geom_utils`, `config`, `ai_v2` (replaces retired `ai_reporter`/`ai_service`).

### Reconciled-profile duality (gotcha)

Two builders, **only the legacy one is re-exported from `core/__init__.py`**:

```python
from core import build_reconciled_profile          # legacy — tuple (distances, elevations, types), emits DeprecationWarning
from core.param_extractor import build_reconciled_profile_v2  # rich ReconciledProfile + ReconciledPoint; NOT in core.__init__
```

Recent parity work (commits G01–G12) added the rich v2 shape (berm-top corners, ramp flags). The API emits **both** `reconciled_design`/`reconciled_topo` (rich v2) and `reconciled_design_legacy`/`reconciled_topo_legacy` (flat `{distances, elevations}`) so the web `ProfileView` can consume the legacy shape. See `docs/UI_PARITY_AUDIT.md` for the G01–G12 gap tracker.

### Drill & Blast (Tronadura)

`core/calculo_tronadura.py` corrects coordinates: `X=Latitud_Geo`, `Y=Longitud_Geo`, `Z_collar=Nombre_Banco+15m`; toe from `Inclinacion_real`/`Azimuth_real`/`longitud_real`. `core/blast_correlation.py` + `param_extractor` project blast holes onto cross-sections and classify berms vs ramps. `openblast/` is a vendor-neutral drill-and-blast interchange schema (v1.0.0, 17 mandatory fields) with mappings for ENAEX/Datamine/Surpac.

### API (`api/`, mounted at `/api/v1`)

Session via `X-Session-ID` header (auto-generated if absent, stored in SQLite). Routers: **meshes** (upload/info/vertices/contours/breaklines), **sections** (CRUD + auto/manual/click/from-file/curve), **process** (run pipeline, status, results, `profiles/{id}`, `profiles/{id}/blast-holes`, editable reconciled), **export** (excel/word/dxf/images), **settings** (tolerances + thresholds), **ai** (health/providers/generate/generate-stream — NDJSON streaming). Auth is a stub (`middleware_auth.py`); rate-limit + CORS middlewares exist.

### Web frontend (`web/`)

`App.tsx → AppLayout → WorkspaceRouter`: Mesh3DViewer → SectionSelector → ProfilesGrid/ProfileView → Dashboard → AIReporter. State: Zustand stores (`session`, `theme`) + TanStack Query (`api/hooks.ts`, axios client in `api/client.ts`). Path alias `@` → `src/`. Vite proxies `/api` → `localhost:8000`. Base path defaults to `/conciliacion-geo-v02/`.

Web quirks: **Cesium is pre-bundled at `web/public/Cesium/` (git-tracked, ~22 MB) — NOT an npm dep, do not add `cesium` to package.json.** PWA via Workbox (runtime-cache only; disable with `VITE_PWA=false` for Electron). Dev server polls the FS by default (avoids inotify ENOSPC on ~33k files). Bilingual i18n (ES/EN).

### Persistence

SQLite (`api/database.py`, `data/conciliacion.db`): tables for meshes, sections, extractions, results, settings, process_status. **Single-machine only — Render free-tier restarts wipe it; ephemeral by design.**

## Configuration (`core/config.py`)

Frozen dataclasses with singleton instances: `TOLERANCES`, `DETECTION`, `DEFAULTS`, `VISUALIZATION`, `RAMP`, `DEPLOY`. Detection defaults: `face_threshold=40°`, `berm_threshold=20°`, `max_berm_width=50m`, `simplify_epsilon=0.05m`, `profile_resolution=0.1m`, `match_threshold=5.0m`, `spill_angle_solid=52°`, `spill_angle_pile=48°`.

Reference design tolerances (source of truth = `core/config.py` `Tolerances`):

| Parameter | Nominal | Tolerance |
|-----------|---------|-----------|
| Bench height | 15 m | −1.0 / +1.5 m |
| Bench face angle | 70° | ±5° |
| Berm width | 9 m | −1.0 / +2.0 m |
| Inter-ramp angle | 48° | −3° / +2° |
| Overall angle | 42° | ±2° |
| Ramp width | 25 m | −2 / +0 m |
| Ramp gradient | 10% | 0 / +2% |

Env vars: `DATABASE_URL`, `CONCILIACION_DATA_DIR`, `CONCILIACION_CORS_ORIGINS`, `CONCILIACION_RATE_LIMIT_ENABLED`, `CONCILIACION_MAX_UPLOAD_MB`; observability `SENTRY_DSN` / `VITE_SENTRY_DSN` / `VITE_ANALYTICS_URL`.

## Conventions & hard constraints

- **`app.py` and `ui/` are OFF-LIMITS** — the maintainer uses the Streamlit app daily. `CONTRIBUTING.md` forbids PRs that touch them; such PRs are rejected. New work goes in `web/` and `api/`, additive only.
- **Code in English** (vars, funcs, docstrings); **UI in Spanish**. Every web UI string must exist in **both** `web/src/locales/es.json` and `en.json` (ICU plurals `_one`/`_other`).
- **Import from `core`, never from submodules** for the re-exported public API — except newer helpers (`build_reconciled_profile_v2`, `azimuth_to_direction`, `generate_sections_along_crest`, `compute_local_azimuth`, anything in `core.geom_utils`) which must be imported from the submodule directly. `api/routers/process.py` and `core/report_generator.py` are the canonical examples.
- **No code comments** unless explicitly requested.
- **Git**: conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`). **No `Co-Authored-By:`**, no AI attribution.
- **Units**: meters, degrees, % (gradient). **Coordinates**: X=East, Y=North, Z=Elevation. **Azimuth**: degrees from North, clockwise.

## Known pitfalls

- `rtree` needs the `libspatialindex` system library — without it, large-mesh AABB ops fail.
- `.gitignore` excludes `.stl`, `.xlsx`, `.db`, `data/`, `dist/`, `web/dist/`, `web/node_modules/`, `electron/dist/`, `*.AppImage`. Test meshes and outputs won't commit.
- Berm detection can produce unrealistic widths (>50 m) on flat areas; partially filtered by `max_berm_width=50`. Ramp detection is partial (width 15–42 m); the "Rampas" Excel sheet may need manual input. Sections near mesh edges can yield incomplete profiles with no warning.
- Electron portable build is two steps (`pyinstaller conciliacion-api.spec` → electron-builder) and **`VITE_PWA=false` is mandatory** during the web build or the service worker breaks the AppImage.
- Test-count badge in `README.md` drifts (was 97/97, now ~114); update both badge and count in PRs that add tests.

## CI (`.github/workflows/`)

On push to main/develop or PR to main — `ci.yml` runs 4 jobs: backend tests (Python 3.12, `pytest tests/` + `test_pipeline.py`), frontend build (Node 20, `tsc --noEmit` + `npm run build`), Docker build (both images, main only), Docker Compose smoke (polls `/api/v1/health`). `deploy-frontend.yml` builds web → GitHub Pages on push to `web/**` of main (copies `index.html` → `404.html` for SPA fallback). **CI does not run vitest or playwright** — run those locally before pushing UI changes.

## Pointers

- `AGENTS.md` — exhaustive command + pitfall quick-reference.
- `ARCHITECTURE.md`, `CONTEXT.md` — system architecture and developer context.
- `docs/UI_PARITY_AUDIT.md` — Streamlit↔web feature-gap tracker (G01–G12).
- `docs/AI_AGENT_V2_BLUEPRINT.md`, `docs/MIGRATION_AI_V2.md` — LLM reporting system.
- `docs/BLAST_ADVISOR.md`, `docs/OPENBLAST_DESIGN.md` — drill & blast engine + open format.
- `docs/SLOPE_STABILITY_AUDIT.md`, `docs/BLAST_DATA_AUDIT.md`, `docs/CLEAN_CODE_AUDIT.md` — domain audit backlogs.
- `docs/PORTABLE.md` — Electron portable bundle design.
