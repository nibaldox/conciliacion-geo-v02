# Architecture

This document describes how the modules of **Conciliación Geotécnica v02** fit
together. For a quick command reference see [AGENTS.md](AGENTS.md); for a
narrative overview see [README.md](README.md).

## High-level

```
                        ┌────────────────────────────┐
                        │  Streamlit UI (app.py)     │
                        │  • Conciliación Geotécnica │
                        │  • Análisis de Tronadura   │
                        └────────────┬───────────────┘
                                     │ CLI / python imports
                                     ▼
┌─────────────────────────────────────────────────────────────┐
│                       core/ (pure business logic)          │
│                                                             │
│  mesh_handler    → load STL/OBJ/PLY/DXF into trimesh       │
│  section_cutter  → SectionLine + cut_mesh_with_section      │
│  param_extractor → RDP + classify + bench detection         │
│                     (uses DetectionDefaults / RAMP)         │
│  excel_writer    → .xlsx (Resumen, Bancos, Tronadura...)    │
│  report_generator→ .docx + section images ZIP               │
│  calculo_tronadura → procesar_pozos, proyectar_pozos       │
│  blast_correlation → shared helper (correlation summary)   │
│  geom_utils      → area, deviation, find_df_column          │
│  config          → frozen dataclasses (Tolerances, ...)     │
│  ai_reporter / ai_service → OpenAI-compatible LLM client   │
└──────────────────────┬──────────────────────────────────────┘
                       │ FastAPI + SQLite session
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  api/   (modular FastAPI app, mounted under /api/v1)        │
│                                                             │
│  routers/                                                   │
│    meshes    → upload, info, vertices, contours, delete     │
│    sections  → CRUD for section lines                       │
│    process   → run pipeline, status, profiles, edits        │
│    export    → excel, word, dxf, images                     │
│    settings  → tolerances, detection thresholds             │
│    ai        → list models, health, generate report         │
│  database.py → SQLite session/result persistence            │
│  main.py     → app factory + session + size-guard + CORS    │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST (X-Session-ID header)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  web/  (React 19 + Vite + CesiumJS, TypeScript)            │
│                                                             │
│  src/api/      client.ts, hooks.ts, types.ts                │
│  src/stores/   zustand: session, theme                      │
│  src/components/  mesh/, sections/, analysis/, results/,    │
│                   export/, layout/                          │
│  e2e/          Playwright tests                             │
└─────────────────────────────────────────────────────────────┘
```

## Data flow

For a single section run, the pipeline is:

1. **Upload** — User POSTs STL/OBJ/DXF to `POST /api/v1/meshes/upload`. The
   raw bytes are stored in SQLite (`api.database.save_mesh`).
2. **Define sections** — User POSTs section definitions to
   `POST /api/v1/sections`. Stored as `SectionLine` records.
3. **Process** — `POST /api/v1/process` runs the pipeline in parallel via
   `ThreadPoolExecutor`:
   - For each section: `cut_both_surfaces` → `extract_parameters` →
     `compare_design_vs_asbuilt`.
   - Extraction results cached per section (for the drag-and-drop editor
     in the UI), and a flat list of comparison rows is persisted.
4. **Browse / edit** — `GET /api/v1/profiles/{section_id}` returns raw
   profiles plus the cached extraction. `PUT /api/v1/results/{section_id}/
   reconciled` accepts user-edited bench positions, recomputes height/angle/
   berm, and re-runs comparison.
5. **Export** — `GET /api/v1/export/{excel|word|dxf|images}` reads the
   cached results and produces the artefact.

For Drill & Blast, the flow is independent and lives mostly in the
Streamlit module:

1. User uploads the ENAEX-format CSV/XLSX from the sidebar of the
   *Análisis de Tronadura* tab.
2. `core.calculo_tronadura.procesar_pozos` normalises coordinates
   (`X=Latitud_Geo`, `Y=Longitud_Geo`, `Z_collar = Nombre_Banco + 15m`),
   drops the ENAEX `COLS_DROP` columns, and computes toe coordinates via
   `Inclination`/`Azimuth` trigonometry.
3. The cleaned DataFrame is overlaid onto any previously computed
   reconciliation sections via
   `proyectar_pozos_en_seccion` (radius `DEFAULTS.blast_correlation_
   radius_m`, default 15 m).
4. `core.blast_correlation.compute_blast_geotech_correlation` produces a
   one-row-per-section summary that is reused by **both** the Excel
   writer and the Word report generator.

## Module boundaries

- **Always import from `core`**, never from `core.submodule`. The
  `core/__init__.py` re-exports the public API.
- **Domain defaults live in `core/config.py`** as frozen dataclasses:
  `Tolerances`, `DetectionDefaults`, `PipelineDefaults`, `VisualizationDefaults`,
  `RampDetection`. UI sliders and CLI args override these at the edge.
- **Status strings are shared via `core/blast_correlation.py`**:
  `STATUS_CUMPLE`, `STATUS_FUERA`, `STATUS_NO_CUMPLE`, `STATUS_NO_CONSTRUIDO`,
  `STATUS_FALTA_BANCO`, `STATUS_EXTRA`. UI code matches these constants
  instead of string literals where possible.

## Persistence

`api/database.py` is a thin SQLite wrapper. Each session (identified by
the `X-Session-ID` header) owns:

- `meshes` (BLOB + metadata)
- `sections` (SectionLine as JSON)
- `extractions` (per-section `ExtractionResult` cache)
- `results` (flat list of comparison dicts)
- `settings` (tolerances, detection thresholds)
- `process_status` (in-flight job status)

This is **single-machine** storage. Scaling out requires a real DB
backend and a shared object store for the mesh BLOBs.

## Concurrency

- The Streamlit UI uses `ThreadPoolExecutor` with default worker count
  for `process_section`. Mesh objects and the executor must remain in
  the main thread — copy meshes before submitting.
- The FastAPI `/process` endpoint also uses a `ThreadPoolExecutor` for
  the same reason. SQLite writes from multiple threads are serialised
  by Python's GIL; concurrent writes from different processes are not
  safe.

## Configuration sources (in order of precedence)

1. CLI args / form body (FastAPI)
2. Session settings in the database
3. Frozen defaults in `core/config.py`

## Known gotchas (see also AGENTS.md)

- `rtree` requires the system library `libspatialindex`. CI installs it
  via `apt-get`; macOS users need `brew install spatialindex`.
- `.streamlit/config.toml` sets `maxUploadSize = 500 MB`. The API enforces
  the same limit via a body-size middleware in `api/main.py`.
- `statmodels` is optional. The OLS trendline in the blast correlation
  tab degrades gracefully when it's missing.
- Berm detection on flat synthetic surfaces can yield unrealistic widths
  (>50 m). `DetectionDefaults.max_berm_width` filters most cases.
