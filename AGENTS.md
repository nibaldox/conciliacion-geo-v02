# AGENTS.md — Conciliación Geotécnica

## Commands

```bash
pip install -r requirements.txt              # Install deps (needs libspatialindex-dev on system)
python test_pipeline.py                      # Run synthetic-pipeline test
streamlit run app.py                         # Start dev server (:8501)
python cli.py --design d.stl --topo t.stl --auto --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0   # CLI batch
python cli.py --design d.stl --topo t.stl --config ejemplo_secciones.json   # CLI with JSON config
```

No lint/typecheck configured. No pre-commit hooks.

## Architecture

```
app.py              Streamlit UI — main entry point
cli.py              CLI batch entry point
core/
  __init__.py       Public re-exports only (import from core, not submodules)
  mesh_handler.py   Load STL/OBJ/PLY/DXF → trimesh, decimate, plotly conversion
  section_cutter.py SectionLine dataclass, cut_mesh_with_section, azimuth helpers
  param_extractor.py Bank/berm detection, angle calculation, design-vs-asbuilt compare
  excel_writer.py   Export to formatted Excel with conditional formatting
  report_generator.py Word report + section images ZIP
  geom_utils.py     Profile deviation, area between profiles
  ai_reporter.py    OpenAI/LM Studio report generation
```

Pipeline: load mesh → define sections (CSV/DXF/manual/auto/interactive) → cut surfaces → extract parameters → compare → export.

## Key Facts

- **Entry point**: `core/__init__.py` — always import from `core`, not `core.module`. E.g. `from core import load_mesh, SectionLine, extract_parameters`.
- **Streamlit session state**: All mutable state lives in `st.session_state`. Use `st.rerun()` after state changes for interactive tab updates.
- **Parallel processing**: Section processing uses `ThreadPoolExecutor` in `app.py`. Never pass Streamlit objects (`st.session_state` references) into worker functions — extract to locals first.
- **Azimuth convention**: Degrees from North, clockwise (N=0, E=90, S=180, W=270).
- **Coordinate system**: East (X), North (Y), Elevation (Z) — standard mining.
- **Test creates temp STLs** in `/tmp/`. No test framework — `test_pipeline.py` is a self-contained script.
- **System dep**: `libspatialindex-dev` required by shapely (deploy on Streamlit Cloud via `packages.txt`).
- **File uploads**: Max 500MB (`.streamlit/config.toml`). Meshes are decimated to 30k faces for 3D viz.
- **Bank matching**: Uses Hungarian algorithm for elevation-based matching between design and as-built benches.
- **Status triad**: CUMPLE / FUERA DE TOLERANCIA (up to 1.5x tolerance) / NO CUMPLE (>1.5x).
- **Known gaps**: Ramp detection not automated. Bench correspondence by index (should be by elevation). Berm width can be unrealistically large on synthetic data.

## Conventions

- Code: English (variables, functions, docstrings).
- UI/labels: Spanish.
- Units: meters, degrees, percentages.
- `.stl` and `.xlsx` files are gitignored.
