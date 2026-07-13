# Capability: streamlit-legacy-surface-integrity

> **Source change**: `streamlit-audit-remediation` (archived)
> **Archived on**: 2026-07-11
> **Status**: archived, source of truth
> **Scope**: New capability. Behavior-preserving remediation of the Streamlit surface (`app.py` + `ui/`).
> **Out of scope**: `web/`, `api/`, `cli.py`, `reconciled-profile-serialization`, deferred M3 (`build_reconciled_profile` → v2).
> **Scope override**: temporarily lifts `openspec/config.yaml#off_limits` for `ui/` per explicit maintainer authorization (one-off, not precedent).

## Purpose

Codify invariants that eliminate two correctness defects, four consistency smells, three deprecation drifts, and four mechanical cleanups. Behavior-preserving: same outputs, same interactions.

## Requirements

### Requirement: Contour cache invalidation on surface reset

The "Limpiar superficies" handler in `ui/step1_upload.py` SHALL call `st.cache_resource.clear()` (and `st.cache_data.clear()`) before nulling mesh references and `st.rerun()`. Acceptable: only `cache_resource` users in `ui/` are `mesh_to_contour_data` (`ui/plots.py:61`) and `_cached_decimate` (`ui/step1_upload.py:20`), both mesh-bound.

#### Scenario: same-grid re-upload produces fresh contour data

- GIVEN mesh `M1` uploaded with `grid_size=50`, contour rendered
- WHEN "Limpiar superficies" → upload `M2` with `grid_size=50`
- THEN next contour render uses `M2`'s data.

#### Scenario: clear precedes rerun

- WHEN clear handler runs
- THEN `st.cache_resource.clear()` runs before mesh-null assignments and `st.rerun()`.

### Requirement: Production code MUST NOT import from `tests/`

`ui/tabs/blast_correlation.py` SHALL import `compute_monthly_trend`, `detect_pf_outliers_iqr`, `split_campaign` from `core.blast_correlation`, never from `tests.test_ai_service_enrich`. The three helpers SHALL live in `core/blast_correlation.py` (additive, no signature changes). The `try/except ImportError` guard at `ui/tabs/blast_correlation.py:28-36` SHALL be removed (unconditional import). `tests/test_ai_service_enrich.py` SHALL re-import from `core.blast_correlation` with byte-identical assertions.

#### Scenario: no tests-imports, helpers resolve, tests pass

- WHEN `rg 'from tests\.' ui/` returns zero
- AND `python -c "from core.blast_correlation import compute_monthly_trend, detect_pf_outliers_iqr, split_campaign"` resolves
- AND `pytest tests/test_ai_service_enrich.py -v` passes
- THEN the move is verified end-to-end.

### Requirement: cached helper purity in section building

`_cached_local_azimuth(ox, oy, mesh_id)` in `ui/step2_sections.py` SHALL NOT reference `st.session_state` inside its cached body. SHALL either hash mesh identity via a `cache_resource` wrapper keyed on `id(mesh)`, OR drop caching (the underlying `compute_local_azimuth` is cheap).

#### Scenario: cache safe across sessions

- GIVEN two session_state instances with `mesh_id=42`
- WHEN `_cached_local_azimuth(0, 0, 42)` called from each
- THEN both return the same value (no session-state reference inside body).

### Requirement: single source of truth for comparison filtering

Inline filter loops in `ui/tabs/dashboard.py`, `ui/tabs/export.py`, `ui/tabs/ai_report.py` SHALL delegate to `ui.filters.apply_comparison_filters` + `ui.filters.filters_summary`. `ui/tabs/table.py:66` is already a consumer (untouched). The local `_filters_summary` reimplementation in `ui/tabs/ai_report.py` SHALL be removed.

#### Scenario: no inline filter loops, ai_report delegates

- WHEN `rg 'df\[["'\'']sector["'\'']\]\.isin' ui/` returns zero
- AND `ui/tabs/ai_report.py` imports `filters_summary` from `ui.filters` (no local `_filters_summary`)
- THEN the SSOT invariant holds.

### Requirement: dead highlight helper removed

`_highlight_status` at `ui/tabs/table.py:101-113` SHALL be deleted. The imported `highlight_status` from `ui.labels` SHALL be preserved.

#### Scenario: only one highlight helper

- WHEN `rg '_highlight_status' ui/`
- THEN zero hits.

### Requirement: berm threshold slider reads detection default

`ui/sidebar.py:38` SHALL be `st.slider("Ángulo máximo berma (°)", 0, 30, int(DETECTION.berm_threshold))`, matching the `face_threshold` pattern on line 37.

#### Scenario: slider default matches config

- GIVEN `DETECTION.berm_threshold = 20`
- WHEN sidebar renders
- THEN slider default is `20`.

### Requirement: shared blast-correlation helper

Duplicated per-section well projection + powder-factor correlation in `ui/modulo_tronadura.py:365-562` and `ui/tabs/blast_correlation.py:47-382` SHALL be extracted into new module `ui/_blast_correlation_shared.py` exposing:

| Function | Signature |
|---|---|
| `project_powder_factor_per_section` | `(profile_design, profile_topo, blasts, polygon) -> pd.DataFrame` |
| `build_pf_damage_scatter` | `(df, ...) -> plotly.Figure` |

Both call sites SHALL import from `ui._blast_correlation_shared`. Module lives in `ui/` (NOT `core/`) because tightly coupled to Streamlit session_state and rendering. Net deletion ~200 LOC. MUST NOT change user-visible behavior (table columns, plot axes, color scales, log lines).

#### Scenario: single definition, both consumers delegate

- WHEN `rg 'def project_section_with_powder_factor|def build_pf_damage_scatter' ui/` returns exactly one hit (in `ui/_blast_correlation_shared.py`)
- AND both `ui/modulo_tronadura.py` and `ui/tabs/blast_correlation.py` import from `ui._blast_correlation_shared`
- THEN the dedup is verified.

### Requirement: section-definition tabs append consistently

All four tabs in `ui/step2_sections.py` (file L128, interactive L268, manual L338, auto L391) SHALL **append** to `st.session_state.sections`. Replace semantics in manual/auto SHALL be removed. On name collision, new entry suffixed `_1`, `_2`, etc. (same pattern as file tab L119-128). Existing "Limpiar lista" button at L424-432 SHALL be preserved.

#### Scenario: manual tab appends

- GIVEN `st.session_state.sections = [sec_a]`
- WHEN user defines manual `sec_b` (unique name)
- THEN `st.session_state.sections == [sec_a, sec_b]`.

#### Scenario: auto tab appends

- GIVEN `st.session_state.sections = [sec_a]`
- WHEN auto generates `[sec_c, sec_d]`
- THEN `st.session_state.sections == [sec_a, sec_c, sec_d]`.

#### Scenario: duplicate name gets suffix

- GIVEN `[Section("A", ...)]`
- WHEN new section named `"A"` added via manual tab
- THEN new entry stored as `Section("A_1", ...)`, existing `"A"` preserved.

#### Scenario: explicit clear preserved

- WHEN user clicks "Limpiar lista" at L432
- THEN `st.session_state.sections == []`.

### Requirement: no `use_container_width` in `ui/` or `app.py`

All call sites in `ui/**` (and any in `app.py`) using `use_container_width=True` SHALL become `width="stretch"` (Streamlit >=1.57 default).

#### Scenario: zero residual hits

- WHEN `rg 'use_container_width' ui/ app.py`
- THEN zero hits.

### Requirement: streamlit.components.v2 import

`ui/tabs/ai_report.py` SHALL import `streamlit.components.v2 as components`. Any `components.html(...)` / `components.iframe(...)` callsite SHALL be verified against v2 API in design phase; if signatures diverge, callsite adjusts to v2 contract.

#### Scenario: zero v1 hits, v2 resolves

- WHEN `rg 'streamlit\.components\.v1' ui/` returns zero
- AND `python -c "import streamlit.components.v2"` resolves
- THEN the migration is verified.

### Requirement: mechanical cleanups (L1–L4)

| ID | Change |
|---|---|
| L1 | Remove redundant `import numpy as np` / `import pandas as pd` in `ui/modulo_tronadura.py` where already imported at module scope |
| L2 | In `ui/tabs/profiles.py`, evict `_profile_figs` cache (`st.session_state['_profile_figs'] = {}`) when `st.session_state.sections` mutates |
| L3 | `z_value: float = None` → `z_value: Optional[float] = None` in `ui/ref_lines.py:108`; import `Optional` if missing |
| L4 | Remove redundant `import os` in `ui/step2_sections.py:107` if `os` is unused after removal |

#### Scenario: cleanup invariants hold

- GIVEN post-change code base
- WHEN `import numpy as np` and `import pandas as pd` each appear at most once in `ui/modulo_tronadura.py`
- AND `_profile_figs` is cleared on any section mutation
- AND `ui/ref_lines.py` declares `z_value: Optional[float] = None` with `Optional` imported
- AND `ui/step2_sections.py` has no `import os` (or it is used)
- THEN all four cleanups are applied.

## Legacy API Compatibility

- `core/__init__.py` re-exports stay intact. Three moved helpers MAY be re-exported additively only.
- `core/blast_correlation.py` gains three top-level functions; no existing signature changes.
- `web/`, `api/`, `cli.py`, `reconciled-profile-serialization` untouched.
- M3 (`build_reconciled_profile` → v2) explicitly deferred; this spec SHALL NOT require v2 adoption.
- `app.py` touched only if a `use_container_width` call lives there (mechanical M1).
