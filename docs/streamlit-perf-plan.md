# Streamlit Performance Plan — `conciliacion-geo-v02`

Date: 2026-06-13
Scope: `app.py` (root) + `ui/` (Streamlit surface)
Off-limits: `core/`, `web/`, `api/`, `cli.py`, `tests/`, `electron/`, `requirements*.txt`, `pyproject.toml`

## Baseline

App is functional after the Q1-Q13 / P6 / P13 batch. User reports "se siente un poco lento". Top causes identified by profiling (in priority order):

1. **Export tabs + blast correlation re-cut meshes** despite `st.session_state.profiles_design` / `profiles_topo` already holding them. ~45s wasted on a 3-export batch, ~15s wasted per tolerance slider drag.
2. **Step 4's 6 tabs re-execute on every rerun** because `st.tabs` is not lazy. Toggling a checkbox in Perfiles triggers full re-cuts in blast_correlation, blast-hole reprojection in ai_report, DataFrame restyling in table. 5-15s per toggle.
3. **Step 1's 3D and contour views run even when collapsed.** ~500-1000ms per rerun building `Mesh3d` traces from 50K+ vertices.

## Phases

Each phase is one commit. Run tests after each: `pytest tests/ -q --tb=short`. Tests target `core/` and `api/` so should be unaffected, but verify.

### Phase 1 — Eliminate redundant `cut_both_surfaces` calls

**Files**: `ui/tabs/export.py`, `ui/tabs/blast_correlation.py`
**Effort**: S | **Risk**: Low | **Impact**: ~45s saved per full export batch, ~15s per tolerance drag

Add a helper `_get_profile_pair(section_name) -> tuple[ProfileResult, ProfileResult] | None` in `ui/tabs/export.py` that looks up `processed_sections` / `profiles_design` / `profiles_topo` by section name. Replace 3 inline calls in `_render_images_export` (line 142), `_render_word_report` (line 230), `_render_dxf_export` (line 316). Same pattern in `ui/tabs/blast_correlation.py:255` — fix the cache key to be tolerant of slider changes (`(tuple(s.name for s in sections), tuple(sorted(blast_df.columns)))` + tolerance, so only the projection step re-runs on slider drag).

### Phase 2 — Cache step-1 figures in session state

**Files**: `ui/step1_upload.py`
**Effort**: S | **Risk**: Low | **Impact**: ~500-1000ms per rerun

Stash the 3D figure in `st.session_state['_3d_fig']` keyed on `id(mesh_design) + id(mesh_topo) + sections_version`. Stash the contour figure in `st.session_state['_contour_fig']` keyed on `(id(mesh_design), id(mesh_topo), config['grid_ref'], contour_int, contour_grid)`. Reconstruct only when the key changes. Build outside the expander — the expander body should just `st.plotly_chart(st.session_state['_3d_fig'], ...)`.

### Phase 3 — Pre-decimate meshes in `_load_meshes`

**Files**: `ui/step1_upload.py`
**Effort**: S | **Risk**: Low | **Impact**: Cleaner code, removes the 2 fallback paths in `_render_3d_view` (lines 150-153) and the duplicated `decimate_mesh` calls in `ui/modulo_tronadura.py:444-461`

In `_load_meshes` (around line 110-127), after loading the full mesh, also decimate and stash BOTH in session state. Remove the per-render fallback that re-decimates if `decimated_mesh_design` is missing.

### Phase 4 — Fix interactive tab double-rerun + missing cache

**Files**: `ui/step2_sections.py`
**Effort**: S | **Risk**: Low | **Impact**: ~1-3s per click in interactive tab

1. Drop the explicit `st.rerun()` at `ui/step2_sections.py:270` (the `on_select="rerun"` on the plotly chart already triggers a rerun).
2. Move `_cached_local_azimuth` (currently at line 30, only used by Tab Manual) to `ui/plots.py` (or a new `ui/_cache.py`). Call it from `_render_tab_interactive:259` (the interactive click handler) — currently the interactive tab calls `compute_local_azimuth` uncached.

### Phase 5 — Vectorize `_add_blast_holes` and cache the projection

**Files**: `ui/tabs/profiles.py`
**Effort**: S | **Risk**: Low | **Impact**: ~200-500ms per profiles-tab rerun with blast data

1. Replace `projected.apply(lambda r: ...)` at lines 460-467 with a vectorized string concatenation (the code already builds `hover_labels = ...` — make it a column expression, not a row apply).
2. Add a `st.session_state['proyectar_pozos_cache']` keyed on `(id(blast_df), tuple(s.origin for s in sections), tuple(s.azimuth for s in sections), tuple(s.length for s in sections))` so repeated profiles-tab renders don't re-project.

### Phase 6 — Precompute unique values in session state

**Files**: `ui/tabs/table.py`, `ui/tabs/dashboard.py`, `ui/tabs/blast_correlation.py`
**Effort**: S | **Risk**: Low | **Impact**: ~100-200ms per step-4 tab rerun

Compute `unique_sectors`, `unique_levels`, `unique_sections`, `unique_benches` ONCE in a small hook (e.g., a `_ensure_filter_values()` helper called from `_render_compliance_table` and friends) and stash in `st.session_state['_filter_values']`. Re-compute only when `comparison_results` changes (track a `comparison_results_id` key).

### Phase 7 — `@st.fragment` for step-4 tabs

**Files**: `ui/step4_results.py`
**Effort**: M | **Risk**: Medium | **Impact**: 5-15s saved per widget change in any tab

Wrap each tab body in `@st.fragment`:
```python
@st.fragment
def _profiles_tab(config: dict):
    render_tab_profiles(config)
```

Call the fragment in the `with tab_X:` block. **Verify** that session_state reads inside fragments still work (they do, but test the "Aplicar" button in step 2's interactive tab — it does `st.session_state.sections.append(...)` which works inside fragments). If something breaks, fall back to per-fragment session_state isolation (use `st.session_state` as usual, no special handling needed).

If a fragment proves too fragile (e.g., the AI report tab is heavy and the per-render feedback gets lost), revert just that one tab and document the issue.

### Phase 8 — `@st.cache_resource` for trimesh objects

**Files**: `ui/step1_upload.py`, `ui/plots.py`
**Effort**: S | **Risk**: Low | **Impact**: Correctness fix + faster repeat calls

The existing `@st.cache_data` decorators on `_cached_decimate` and `mesh_to_contour_data` have underscore-prefixed args (`_mesh`) which bypass Streamlit's hash. The cache key collapses to a positional integer, so different meshes can return stale results. Switch to `@st.cache_resource` (in-memory, no pickle, supports unhashable objects). The cache key for `_cached_decimate` becomes `(id(mesh), target_faces)`. For `mesh_to_contour_data`, the key is already `(_mesh, n)` — just change the decorator.

### Phase 9 — `procesar_pozos` in thread (D&B module)

**Files**: `ui/modulo_tronadura.py`
**Effort**: S | **Risk**: Low | **Impact**: ~1-5s perceived latency for the "Procesar Pozos" button

The "Procesar Pozos" button at line 62-73 calls `procesar_pozos(df)` synchronously in the main thread. Wrap it in a `concurrent.futures.ThreadPoolExecutor` (same pattern as `ui/step3_analysis.py:91-103`) and use `st.progress` / `st.status` for feedback. Capture session-state into local vars before handing to the worker, restore results on completion.

### Phase 10 — Precompute reconciled + area data once

**Files**: `ui/step3_analysis.py`, `ui/tabs/profiles.py`
**Effort**: M | **Risk**: Medium | **Impact**: ~1-3s per step-4 tab rerun

Step 4's profiles tab calls `build_reconciled_profile` per figure × N sections (= 2N calls on 10 sections). Pre-compute the reconciled profile and area-fill arrays in step 3 and stash in `st.session_state['reconciled_design']` / `reconciled_topo` / `area_fill_design` / `area_fill_topo`. The profiles tab reads from session state instead of recomputing.

This is a step-3 ↔ step-4 API change. Verify that the step-4 tabs gracefully handle the case where step-3 hasn't run yet (return empty figures or skip).

## Commit sequence

| # | Phase | Subject | Net |
|---|---|---|---|
| 1 | 1 | perf(ui): cache cut_both_surfaces via session state | -30 LOC (replaces 3 inline cuts with helper) |
| 2 | 2+3 | perf(ui): cache step-1 3D/contour figures in session state, pre-decimate on load | +30 / -25 |
| 3 | 4 | fix(ui): drop double-rerun and missing cache in interactive tab | -3 / +3 |
| 4 | 5 | perf(ui): vectorize blast-hole hover labels, cache projection | -8 / +5 |
| 5 | 6 | perf(ui): precompute filter unique values in session state | +25 / -10 |
| 6 | 7 | perf(ui): wrap step-4 tabs in @st.fragment for partial reruns | +25 / -10 |
| 7 | 8 | fix(ui): use @st.cache_resource for trimesh objects (cache_key collapse bug) | +3 / -3 |
| 8 | 9 | perf(ui): run procesar_pozos in a thread with progress feedback | +15 / -5 |
| 9 | 10 | perf(ui): precompute reconciled profile and area-fill in step 3 | +20 / -30 |

## Verification

After each commit:
```bash
cd /home/xod/Documentos/Code/conciliacion-geo-v02 && source .venv/bin/activate && python -m pytest tests/ -q --tb=short 2>&1 | tail -3
```
Expect 114 passed, 1 warning (pre-existing StarletteDeprecationWarning in testclient).

After all commits, the user tests in their actual `streamlit run app.py` (Python 3.14 venv, separate from the test venv) and reports.

## Defer / not in scope

- **B5 (replace st.tabs with st.radio)**: superseded by Phase 7 fragments.
- **B8 (downsample 3D mesh to 10K)**: visual choice; defer to user feedback.
- **i18n keys for blast advisory thresholds** (from earlier review): no perf impact.
- **P14 (smoke tests for ui/)**: separate concern, separate plan.
- **Site-specific magic numbers to core/config.py** (from earlier review): out of scope (core/ is off-limits).
