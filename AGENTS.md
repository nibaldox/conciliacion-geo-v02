# AGENTS.md

## Project

Geotechnical reconciliation tool for open-pit mine slopes. Compares 3D design surfaces vs as-built topography (STL/OBJ/DXF), generates cross-sections, extracts bench parameters, evaluates compliance against tolerances.

**Stack**: Python 3.10+, Streamlit, FastAPI, trimesh, numpy, scipy, plotly, openpyxl
**Web frontend**: React 19, Vite 6, TypeScript, Tailwind CSS 4, CesiumJS, Chart.js, Zustand, TanStack Query/Table
**Deploy**: Docker Compose (FastAPI + nginx for React) — `docker-compose.yml`

---

## Commands

```bash
# Install Python deps (system lib needed: libspatialindex-dev / brew install spatialindex)
pip install -r requirements.txt          # Streamlit + all deps
pip install -r requirements-api.txt      # FastAPI-only subset
pip install -e .                         # editable install (uses pyproject.toml)

# Tests
python -m pytest tests/ -v --tb=short               # unit tests (pytest, pythonpath="." in pyproject.toml)
python test_pipeline.py                              # integration test with synthetic surfaces
python -m pytest tests/test_param_extractor.py::TestParamExtractor::test_extract_parameters -v

# Streamlit UI
streamlit run app.py

# FastAPI backend (for web frontend)
uvicorn api.main:app --reload --port 8000

# Web frontend (from web/)
cd web && npm ci && npm run dev          # dev server :5173, proxies /api → :8000
cd web && npm run build                  # tsc + vite build
cd web && npx tsc --noEmit               # typecheck only

# Start both backend + frontend
bash dev.sh

# CLI batch
python cli.py --design diseno.stl --topo topo.stl --auto --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0 --length 200
python cli.py --design diseno.stl --topo topo.stl --config ejemplo_secciones.json
```

No Python linter/formatter configured. Web frontend has ESLint (`npm run lint` in `web/`).

---

## Architecture

Three interfaces share the same `core/` package:

- **Streamlit** (`app.py` + `ui/` modules) — monolithic interactive UI, primary interface
- **React + FastAPI** (`web/` + `api/`) — decoupled frontend; Vite/React/TypeScript app calls FastAPI REST API
- **CLI** (`cli.py`) — batch automation

### Directories

```
core/          Business logic — import from core, NEVER from submodules
api/           FastAPI backend (modular: main.py + routers/)
  routers/       meshes, sections, process, export, settings, ai
  database.py    SQLite session management
  schemas.py     Pydantic models
app/           Streamlit app (refactored modules)
ui/            Streamlit UI components (step1_upload, step2_sections, ...)
web/           React frontend (TypeScript, CesiumJS, Tailwind)
  src/
    api/          client.ts, hooks.ts, types.ts
    components/   mesh/, sections/, analysis/, results/, export/, layout/
    stores/       session.ts (zustand), theme.ts
tests/         pytest suite (conftest.py + 5 test modules)
```

### Drill & Blast (Tronadura) module

`app.py` is a router with sidebar navigation between two top-level modules:

- **Conciliación Geotécnica** (`ui/modulo_conciliacion.py`) — original geotech reconciliation flow
- **Análisis de Tronadura** (`ui/modulo_tronadura.py`) — drill & blast analysis

Blast module key files:

- `core/calculo_tronadura.py` — pure-math blast-hole processing. Coordinate correction: `X=Latitud_Geo`, `Y=Longitud_Geo`, `Z_collar=Nombre_Banco+15m`. Toe calculated from `Inclinacion_real`/`Azimuth_real`/`longitud_real`. Drops ENAEX columns marked "no usar" (see `COLS_DROP`).
- `ui/ref_lines.py` — shared multi-file CSV uploader for mesh boundaries (mallas); traces stored in `st.session_state.ref_line_traces` so any module can overlay them.
- `ui/tabs/blast_correlation.py` — cross-section blast-hole overlay (holes projected onto profiles with tolerance control, hover info, collar markers).
- `ui/tabs/profiles.py` — also handles blast-hole projection onto reconciliation cross-sections.

### Pipeline

1. `load_mesh(filepath)` → trimesh mesh
2. `cut_mesh_with_section(mesh, section)` → ProfileResult (distances, elevations)
3. `extract_parameters(distances, elevations)` → ExtractionResult (benches, angles)
4. `compare_design_vs_asbuilt(params_d, params_t, tolerances)` → list of comparison dicts
5. `export_results(...)` → Excel / Word / DXF

### API routes

All mounted under `/api/v1/*`. Session via `X-Session-ID` header (middleware auto-assigns UUID). Key endpoints: `/meshes/upload`, `/sections/*`, `/process`, `/results`, `/export/excel`, `/export/dxf`.

### Web frontend

- Vite dev server proxies `/api` → `localhost:8000`
- CesiumJS assets copied from `node_modules/cesium` to `public/Cesium` via custom Vite plugin
- Path alias: `@` → `src/`
- E2E tests: Playwright (`web/e2e/`)

---

## CI

`.github/workflows/ci.yml` runs on push to main/develop and PRs to main:
1. **Backend tests**: Python 3.12, `pip install -r requirements-api.txt && pip install -e .`, then `pytest` + `test_pipeline.py`
2. **Frontend build**: Node 20, `npm ci` in `web/`, `tsc --noEmit`, `npm run build`
3. **Docker build**: builds `Dockerfile-api` and `Dockerfile-web` (only on push to main)

---

## Key Conventions

- **Code language**: English (variables, functions, docstrings)
- **UI language**: Spanish (labels, titles, user-facing strings)
- **Units**: meters, degrees, percentage (gradients)
- **Coordinates**: X=East, Y=North, Z=Elevation (mining standard)
- **Azimuth**: degrees from North, clockwise (N=0, E=90, S=180, W=270)
- **No comments in code** unless explicitly requested
- **Git commits**: conventional `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- No "Co-Authored-By" or AI attribution in commits

### Imports (critical rule)

```python
from core import load_mesh, SectionLine, extract_parameters   # correct
from core.mesh_handler import load_mesh                        # wrong
```

### Bench evaluation

Three-tier: CUMPLE (within tolerance) → FUERA DE TOLERANCIA (up to 1.5x) → NO CUMPLE (exceeds 1.5x).
Bench matching uses Hungarian algorithm on elevation (`scipy.optimize.linear_sum_assignment`).

---

## Configuration

`core/config.py` has frozen dataclasses with all defaults: `Tolerances`, `DetectionDefaults`, `PipelineDefaults`, `VisualizationDefaults`, `RampDetection`.

`packages.txt` lists `libspatialindex-dev` (system dep for rtree, needed for AABB spatial filtering on large meshes).

`.streamlit/config.toml` sets `maxUploadSize = 500` MB.

---

## Known Pitfalls

- `rtree` requires `libspatialindex` system library. Without it, large mesh operations fail. On macOS: `brew install spatialindex`.
- `.gitignore` excludes `.stl` and `.xlsx` — test meshes and outputs won't be committed.
- API session store uses SQLite (`api/database.py`) — improved from in-memory but still single-machine.
- Berm detection can produce unrealistic widths (>50m) on flat areas. Partially filtered by `max_berm_width=50`.
- Ramp detection is partial (width range 15-42m). The "Rampas" Excel sheet may need manual input.
- Sections near mesh edges can produce incomplete profiles with no user warning.
- `frontend/` directory exists alongside `web/` — `web/` is the active React frontend. `frontend/` is an older/alternative version.
- `app.py` (root) still exists but the Streamlit app is also split into `app/` package with `app/app.py`.
- `api/main_legacy.py` is the old monolithic API — the active one is `api/main.py` with routers.
