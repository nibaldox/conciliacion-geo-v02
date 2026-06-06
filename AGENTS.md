# AGENTS.md

Geotechnical reconciliation for open-pit mine slopes. Compares 3D design vs as-built surfaces (STL/OBJ/DXF), generates cross-sections, extracts bench parameters, evaluates compliance against tolerances.

**Stack**: Python 3.10+, trimesh, numpy/scipy, FastAPI, Streamlit, openpyxl, python-docx, ezdxf
**Web frontend**: React 19, Vite 6, TypeScript, Tailwind CSS 4, CesiumJS, Chart.js, Zustand, TanStack Query/Table, Plotly
**Deploy**: GitHub Pages (web/ frontend) + Render.com free tier (API Docker), legacy Streamlit

---

## Commands

```bash
# System dep required: libspatialindex-dev (apt) / brew install spatialindex (macOS)
pip install -r requirements.txt       # full Stacklit
pip install -r requirements-api.txt   # API-only
pip install -e .                      # editable install

pytest tests/ -v --tb=short                                     # unit tests
pytest tests/test_param_extractor.py::TestParamExtractor::test_extract_parameters -v
python test_pipeline.py                                         # integration / synthetic surfaces

uvicorn api.main:app --reload --port 8000                       # API dev server
streamlit run app.py                                            # legacy Streamlit UI (do NOT modify)

cd web && npm ci && npm run dev                                  # frontend dev :5173
cd web && npx tsc --noEmit                                       # typecheck
cd web && npm run build                                          # tsc + vite build
cd web && npm run test                                           # vitest (100% domain coverage required)
cd web && npm run lint                                           # ESLint

bash dev.sh                                                      # API + frontend simultaneously

python cli.py --design diseno.stl --topo topo.stl --auto --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0 --length 200
python cli.py --design diseno.stl --topo topo.stl --config ejemplo_secciones.json
```

---

## Architecture

Three interfaces share `core/` — **always import from `core`, NEVER from submodules**:
```python
from core import load_mesh, SectionLine, extract_parameters   # correct
from core.mesh_handler import load_mesh                        # wrong
```

| Layer | Dir | Entrypoint |
|-------|-----|------------|
| Domain (shared) | `core/` | `__init__.py` re-exports public API |
| API (FastAPI, modular) | `api/` | `api/main.py` — routers: meshes, sections, process, export, settings, ai |
| Web frontend (active dev) | `web/` | Vite + React 19, proxies `/api` → `:8000`, PWA |
| Streamlit (LEGACY, OFF-LIMITS) | `app.py` + `ui/` | Maintainer forbids changes |

**Key core modules**: `mesh_handler`, `section_cutter`, `param_extractor`, `excel_writer`, `report_generator`, `calculo_tronadura`, `blast_correlation`, `geom_utils`, `ai_reporter`, `ai_service`, `config`
**Tests**: 9 modules in `tests/` (pytest, `pythonpath="."` in pyproject.toml)

### Drill & Blast (Tronadura)

- `core/calculo_tronadura.py` — coordinate correction: `X=Latitud_Geo`, `Y=Longitud_Geo`, `Z_collar=Nombre_Banco+15m`; toe from `Inclinacion_real`/`Azimuth_real`/`longitud_real`
- `ui/modulo_tronadura.py` + `ui/tabs/blast_correlation.py` — cross-section blast-hole overlay
- `ui/ref_lines.py` — shared CSV mesh-boundary uploader; traces in `st.session_state.ref_line_traces`

### Pipeline

1. `load_mesh(filepath)` → trimesh mesh
2. `cut_mesh_with_section(mesh, section)` → ProfileResult (distances, elevations)
3. `extract_parameters(distances, elevations)` → ExtractionResult (benches: RDP → angle classification → merge; Hungarian matching for design vs as-built)
4. `compare_design_vs_asbuilt(params_d, params_t, tolerances)` → three-tier compliance: **CUMPLE** (within tol) → **FUERA DE TOLERANCIA** (≤1.5× tol) → **NO CUMPLE** (>1.5× tol)
5. `export_results(...)` → Excel / Word / DXF

### API

Mounted under `/api/v1/*`. Session via `X-Session-ID` header. Key env vars from `render.yaml` / `core/config.py`:
- `DATABASE_URL`, `CONCILIACION_DATA_DIR`, `CONCILIACION_CORS_ORIGINS`, `CONCILIACION_RATE_LIMIT_ENABLED`, `CONCILIACION_MAX_UPLOAD_MB`
- Observability: `SENTRY_DSN` (both Python + JS via `VITE_SENTRY_DSN`), `VITE_ANALYTICS_URL`

### Web frontend quirks

- **Cesium asset issue**: `node_modules/cesium/Build/Cesium` → `public/Cesium` via custom Vite plugin at build time (~22 MB, excluded from PWA precache)
- **PWA**: Workbox SW, runtime-caching only (no precache), `navigateFallbackDenylist` for `/Cesium/*` paths
- **Dev server polls file system** by default (avoids ENOSPC on `inotify`). Set `VITE_USE_NATIVE_WATCH=true` to override.
- **Vite proxy**: `/api` → `localhost:8000`
- **Path alias**: `@` → `src/`

---

## CI (`.github/workflows/ci.yml`)

On push to main/develop or PR to main — 4 parallel jobs:
1. **Backend tests**: Python 3.12, `libspatialindex-dev` system dep, `pytest` + `test_pipeline.py`
2. **Frontend build**: Node 20, `npm ci` → `tsc --noEmit` → `npm run build`
3. **Docker build**: builds both `Dockerfile-api` + `Dockerfile-web` (main only)
4. **Docker Compose smoke test**: healthcheck waits up to 60s for `/api/v1/health` 200

**GitHub Pages deploy** (`.github/workflows/deploy-frontend.yml`): on push to main, builds web/ with env vars (`VITE_BASE`, `VITE_API_URL`, `VITE_SENTRY_DSN`, `VITE_ANALYTICS_URL`), copies `dist/index.html` → `dist/404.html` for SPA fallback.

---

## Key Conventions

- **Code language**: English (variables, functions, docstrings)
- **UI language**: Spanish (labels, titles, user-facing strings)
- **i18n**: every UI string in BOTH `web/src/locales/es.json` + `en.json`; ICU plurals (`_one` / `_other`)
- **Units**: meters, degrees, percentage (%)
- **Coordinates**: X=East, Y=North, Z=Elevation (mining standard)
- **Azimuth**: degrees from North, clockwise (N=0, E=90, S=180, W=270)
- **No comments in code** unless requested
- **Git**: conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`). No `Co-Authored-By:`, no AI attribution.
- **No Python linter/formatter configured**. Frontend has ESLint (`npm run lint` in `web/`).

---

## Configuration

All defaults in `core/config.py` — frozen dataclasses (`Tolerances`, `DetectionDefaults`, `PipelineDefaults`, `VisualizationDefaults`, `RampDetection`, `DeployDefaults`). Singleton instances (`DEFAULTS`, `DETECTION`, `TOLERANCES`, `VISUALIZATION`, `RAMP`, `DEPLOY`).

Key detection defaults: `face_threshold=40°`, `berm_threshold=20°`, `max_berm_width=50m`, `simplify_epsilon=0.1m`, `match_threshold=5.0m`.

`.streamlit/config.toml` sets `maxUploadSize = 500MB`.

---

## Known Pitfalls

- `rtree` requires `libspatialindex` system library. Without it, large-mesh AABB operations fail.
- `.gitignore` excludes `.stl` and `.xlsx` — test meshes and outputs won't commit.
- API session store uses SQLite (`api/database.py`) — single-machine only.
- Berm detection can produce unrealistic widths (>50m) on flat areas. Partially filtered by `max_berm_width=50`.
- Ramp detection is partial (width range 15-42m). The "Rampas" Excel sheet may need manual input.
- Sections near mesh edges can produce incomplete profiles with no user warning.
- `app.py` (root) still exists but **must not be modified** — README/CONTRIBUTING explicitly forbid it.
- Cesium dependency must stay excluded from Vite's `optimizeDeps` due to CJS/ESM mixed structure. Transitive CJS deps listed in `optimizeDeps.include`.
