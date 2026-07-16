# AGENTS.md

Geotechnical reconciliation for open-pit mine slopes. Compares 3D design vs as-built surfaces (STL/OBJ/DXF), generates cross-sections, extracts bench parameters, evaluates compliance against tolerances.

**Stack**: Python 3.10+, trimesh, fast_simplification, numpy/scipy, FastAPI, Streamlit, openpyxl, python-docx, ezdxf
**Web frontend**: React 19, Vite 6, TypeScript, Tailwind CSS 4, CesiumJS, Plotly, three.js, Chart.js, Zustand, TanStack Query/Table, i18next
**Deploy**: GitHub Pages (web/) + Render.com free tier (API Docker) + Electron portable AppImage

---

## Commands

```bash
# System dep: libspatialindex-dev (apt) / brew install spatialindex (macOS)
pip install -e .                      # editable install (uses pyproject.toml)
pip install -r requirements-api.txt   # API-only deps

pytest tests/ -v --tb=short                                # all unit tests (~772 collected; --ignore=tests/test_openblast.py if openblast pkg missing)
pytest tests/test_param_extractor.py::TestParamExtractor::test_extract_parameters -v
python test_pipeline.py                                     # synthetic end-to-end

uvicorn api.main:app --reload --port 8000                  # API dev server
streamlit run app.py                                       # legacy UI (do NOT modify, see Architecture)
bash dev.sh                                                # API + web in one shell

cd web && npm ci && npm run dev                            # frontend dev :5173
cd web && npx tsc --noEmit                                 # typecheck
cd web && npm run build                                    # tsc + vite build (PWA on)
VITE_PWA=false npm run build                               # build without service worker (electron bundle) — set env BEFORE the command
cd web && npm run test                                     # vitest (100% domain coverage required on src/components/results/ProfileView/domain)
cd web && npm run test:e2e                                 # playwright (needs API + web running)
cd web && npm run lint                                     # ESLint

python cli.py --design diseno.stl --topo topo.stl --auto --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0 --length 200
python cli.py --design diseno.stl --topo topo.stl --config ejemplo_secciones.json
```

---

## Architecture

Three interfaces share `core/` — **always import from `core`, never from submodules** for the legacy stable public API:
```python
from core import load_mesh, SectionLine, extract_parameters   # correct
from core.mesh_handler import load_mesh                        # wrong
```

| Layer | Dir | Entrypoint |
|-------|-----|------------|
| Domain (shared) | `core/` | `__init__.py` re-exports the legacy stable API only (see "Import rules") |
| API (FastAPI) | `api/` | `api/main.py` — routers: meshes, sections, process, export, settings, ai |
| Web frontend (active dev) | `web/` | Vite + React 19, proxies `/api` → `:8000`, PWA |
| Streamlit (LEGACY, OFF-LIMITS) | `app.py` + `ui/` | Maintainer uses these daily; PRs touching them will be rejected |
| Electron portable bundle | `electron/` | PyInstaller API sidecar + web build → AppImage / Windows installer |
| Blast simulator (optional) | `openblast/` | Needed only for `tests/test_openblast.py` (skip with `--ignore`) |

**Key core modules**: `mesh_handler`, `section_cutter`, `param_extractor` (compat shim → `profile_simplify`, `profile_extract`, `bench_classify`, `profile_compliance`), `excel_writer`, `report_generator`, `calculo_tronadura`, `blast_correlation`, `blast_metrics`, `blast_model`, `blast_advisor`, `stability_analysis`, `alert_system`, `geology`, `explosive_properties`, `column_utils`, `compliance_status`, `geom_utils`, `breaklines`, `ai_v2/` (replaces retired `ai_reporter`/`ai_service`), `config`.
**Tests**: pytest, `pythonpath="."` in `pyproject.toml`.

### Import rules — gotcha

`core/__init__.py` re-exports only the **legacy/stable** public API. Newer helpers must be imported from the submodule directly:

```python
from core import build_reconciled_profile          # OK — legacy (emits DeprecationWarning, tuple output)
from core.param_extractor import build_reconciled_profile_v2   # OK — required, NOT in core.__init__
```

Other symbols you must import from the submodule: `azimuth_to_direction`, `generate_sections_along_crest`, `compute_local_azimuth`, anything in `core.geom_utils`, anything under `core.ai_v2`. Canonical examples: `api/routers/process.py` and `core/report_generator.py`.

### Drill & Blast (Tronadura)

- `core/calculo_tronadura.py` — coordinate correction: `X=Latitud_Geo`, `Y=Longitud_Geo`, `Z_collar=Nombre_Banco+15m`; toe from `Inclinacion_real`/`Azimuth_real`/`longitud_real`.
- `core/blast_correlation.py` + `core/blast_metrics.py` — projects blast holes onto cross-sections, computes PF / stemming ratio / kg/m, classifies berms as ramps.
- Legacy UI lives in `ui/modulo_tronadura.py` + `ui/tabs/blast_correlation.py` (off-limits with `app.py`/`ui/`).

### Pipeline

1. `load_mesh(filepath)` → trimesh mesh (`core.mesh_handler`)
2. `cut_mesh_with_section(mesh, section)` → `ProfileResult` (distances, elevations)
3. `extract_parameters(distances, elevations)` → `ExtractionResult` (RDP → angle classification → merge; Hungarian matching for design vs as-built)
4. `compare_design_vs_asbuilt(params_d, params_t, tolerances)` → three-tier compliance: **CUMPLE** (within tol) → **FUERA DE TOLERANCIA** (≤1.5× tol) → **NO CUMPLE** (>1.5× tol)
5. `export_results(...)` / `generate_word_report(...)` / `generate_section_images_zip(...)` → Excel / Word / DXF / PNG zip

### API

Mounted under `/api/v1/*`. Session via `X-Session-ID` header (auto-generated if absent, stored in SQLite). Env vars read in `core/config.py` / `render.yaml`:
- `CONCILIACION_DATA_DIR`, `CONCILIACION_CORS_ORIGINS`, `CONCILIACION_RATE_LIMIT_ENABLED`, `CONCILIACION_RATE_LIMIT_PER_MIN`, `CONCILIACION_MAX_UPLOAD_MB`, `CONCILIACION_LOG_LEVEL`, `CONCILIACION_LOG_FORMAT`, `CONCILIACION_WORKERS`, `CONCILIACION_USE_SUPABASE`, `CONCILIACION_USE_R2`, `CONCILIACION_AUTH_REQUIRED`
- Observability: `SENTRY_DSN` (backend) + `VITE_SENTRY_DSN` + `VITE_ANALYTICS_URL` (frontend)

### Web frontend quirks

- **Cesium**: shipped pre-bundled at `web/public/Cesium/` (git-tracked, ~22 MB, gitignored from PWA precache via `globIgnores`). **Not** a node_module dep — do not add `cesium` to `package.json`.
- **PWA**: Workbox SW, runtime-caching only (no Cesium/Plotly precache). Disable for Electron portable builds: `VITE_PWA=false npm run build`. SPA fallback: `dist/404.html` is copied from `dist/index.html` in the deploy workflow.
- **Base path**: default `/conciliacion-geo-v02/`. For custom domain, set `VITE_BASE=/` in repo secrets.
- **Dev server polls file system** by default to avoid `inotify` ENOSPC on `node_modules` (~33K files). Override with `VITE_USE_NATIVE_WATCH=true` if you've bumped the watcher limit.
- **Vite proxy**: `/api` → `localhost:8000`. Path alias: `@` → `src/`.
- **Rollup native bin**: `package.json#optionalDependencies` lists per-platform `@rollup/rollup-*-gnu` / `-msvc`; if `npm run dev` errors with `Cannot find module '@rollup/rollup-linux-x64-gnu'`, install the matching binary manually (see README troubleshooting).
- **Domain coverage is enforced at 100%** for `web/src/components/results/ProfileView/domain/**` only — other layers are aspirational. Run `npm run test:domain` to scope vitest to that subtree.

---

## CI (`.github/workflows/ci.yml`)

On push to main/develop or PR to main — 4 parallel jobs:
1. **Backend tests**: Python 3.12, `libspatialindex-dev` system dep, `pytest tests/` + `python test_pipeline.py`
2. **Frontend build**: Node 20, `npm ci` → `tsc --noEmit` → `npm run build`
3. **Docker build**: builds both `Dockerfile-api` + `Dockerfile-web` (main only)
4. **Docker Compose smoke test**: healthcheck polls `/api/v1/health` up to 60s for `healthy` status

**GitHub Pages deploy** (`.github/workflows/deploy-frontend.yml`): on push to `web/**` of main, builds with env vars (`VITE_BASE`, `VITE_API_URL`, `VITE_SENTRY_DSN`, `VITE_ANALYTICS_URL`, `VITE_RELEASE`), then copies `dist/index.html` → `dist/404.html` for SPA routing fallback.

Note: CI does **not** run frontend `npm run test` (vitest) or `npm run test:e2e` (playwright). Run those locally before pushing UI changes.

---

## Key Conventions

- **Code language**: English (variables, functions, docstrings)
- **UI language**: Spanish (labels, titles, user-facing strings)
- **i18n**: every UI string in BOTH `web/src/locales/es.json` + `en.json`; ICU plurals (`_one` / `_other`)
- **Units**: meters, degrees, percentage (%)
- **Coordinates**: X=East, Y=North, Z=Elevation (mining standard)
- **Azimuth**: degrees from North, clockwise (N=0, E=90, S=180, W=270)
- **No comments in code** unless requested
- **Git**: conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`). **No `Co-Authored-By:`**, no AI attribution.
- **Python**: follow PEP 8, type hints on public functions, prefer the frozen dataclasses in `core/config.py` over magic numbers. **No Python linter/formatter configured.** Frontend has ESLint (`web/`) and TypeScript strict mode.
- **CSS**: Tailwind utility classes; theme tokens (`--color-*`, `--status-*`) instead of raw hex.

---

## Configuration

All defaults in `core/config.py` — frozen dataclasses (`Tolerances`, `DetectionDefaults`, `PipelineDefaults`, `VisualizationDefaults`, `RampDetection`, `DeployDefaults`, `ExplosiveEnergy`, `PowderFactor`, `BlastAdvisorDefaults`, `StabilityDefaults`, `SectorDeviationDefaults`). Singleton instances (`DEFAULTS`, `DETECTION`, `TOLERANCES`, `VISUALIZATION`, `RAMP`, `DEPLOY`, `EXPLOSIVE`, `POWDER_FACTOR`, `ADVISOR`, `STABILITY`, `SECTOR_DEVIATION`).

Key detection defaults: `face_threshold=40°`, `berm_threshold=20°`, `max_berm_width=50m`, `simplify_epsilon=0.05m`, `profile_resolution=0.1m`, `match_threshold=5.0m`, `spill_angle_solid=52°`, `spill_angle_pile=48°`.

`.streamlit/config.toml` sets `maxUploadSize = 500MB` + `fileWatcherType = "poll"`.

---

## Known Pitfalls

- `rtree` requires `libspatialindex` system library. Without it, large-mesh AABB operations fail. Install via `apt-get install libspatialindex-dev` (Linux) or `brew install spatialindex` (macOS).
- `.gitignore` excludes `.stl`, `.xlsx`, `.db`, `data/`, `dist/`, `web/dist/`, `web/node_modules/`, `electron/dist/`, `*.AppImage`. Test meshes and outputs won't commit.
- **API session store is SQLite** (`api/database.py`) — single-machine only. Render free tier restarts wipe it; ephemeral by design (`render.yaml` documents this).
- Berm detection can produce unrealistic widths (>50m) on flat areas. Partially filtered by `max_berm_width=50`.
- **Reconciled profile API split**:
  - `core.param_extractor.build_reconciled_profile(...)` — legacy tuple output, emits `DeprecationWarning`.
  - `core.param_extractor.build_reconciled_profile_v2(benches, source="topo")` — returns a rich `ReconciledProfile` with `ReconciledPoint` entries. Berms are explicit horizontal segments via a `berm_top` point; ramps (`is_ramp=True`) skip the berm corner and emit a `ramp` point.
  - The v2 helper is **not** re-exported from `core/__init__.py` — import it from `core.param_extractor` directly.
- Ramp detection is partial (width range 15-42m). The "Rampas" Excel sheet may need manual input.
- Sections near mesh edges can produce incomplete profiles with no user warning.
- **`app.py` (root) and `ui/` are off-limits** — the maintainer uses them daily for real work. `CONTRIBUTING.md` mentions `core/` and `cli.py` too, but in practice those are shared domain where changes happen; the rule that actually holds is: changes to `core/` are welcome if they preserve the legacy stable API re-exported by `core/__init__.py`. New work goes into `web/` and `api/`, additive only.
- **Streamlit file watcher**: `fileWatcherType = "poll"` is set in `.streamlit/config.toml` to avoid `inotify` ENOSPC; don't switch to default `auto` on systems with many small files.
- **Electron portable build requires two steps**: `pyinstaller conciliacion-api.spec` → `electron-builder` in `electron/`. The `VITE_PWA=false` env var is mandatory during the web build step or the SW will break the AppImage.
- **Test counts shift**: ~772 collected as of writing. The `633/633` badge in `README.md` is stale; update it (and the count in coverage tables) in PRs that add tests.
- **`openblast` is an optional dependency** — `tests/test_openblast.py` errors at collection if the simulator package isn't installed. Use `--ignore=tests/test_openblast.py` to skip in that case.
