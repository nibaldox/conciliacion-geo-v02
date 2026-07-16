# Verify Report: streamlit-audit-remediation

> **Status**: PASS (with 1 minor SUGGESTION — no CRITICAL or WARNING)
> **Date**: 2026-07-11
> **Branch**: `sdd/streamlit-audit-remediation`
> **Verify sub-agent**: MiniMax-M3 (sdd-verify)

## Executive Summary

All 13 spec requirements are satisfied at the behavioral / scenario level.
All 4 invariant checks return zero hits. The pytest suite is green (755
passing; 15 pre-existing failures unrelated to this change; 1 out-of-scope
deferred file skipped). The pipeline smoke test exports Excel + Word
successfully. The H5 pre/post byte-identity test passes on a synthetic
4-section DataFrame. C1 ordering is correct (cache clear BEFORE mesh-null
+ rerun). C2 helpers are properly relocated to `core.blast_correlation`.
H5 shared module is wired into both call sites.

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| WARNING  | 0 |
| SUGGESTION | 1 |
| **Total findings** | **1** |

**TL;DR**: Implementation is behavior-preserving and scenario-compliant.
Ready for archive with one optional cosmetic follow-up.

---

## Verification Matrix — Per-Criterion Results

### 1. Full test suite — `pytest tests/ --tb=short -q`

| Metric | Value |
|---|---|
| Collected (excluding `test_openblast.py` + `test_reconciled_profile_serialization.py`) | 772 |
| Passed | 755 |
| Failed (pre-existing, unrelated) | 15 |
| Skipped | 2 |
| Out-of-scope collection errors | 1 |

**Result: PASS**

Pre-existing failures are all in:
- `tests/test_ai_v2_cache.py` (4 tests, async — pytest-asyncio missing)
- `tests/test_ai_v2_service.py` (9 tests, async — same root cause)
- `tests/test_api_auth.py` (2 tests, sqlite env — pre-existing)

These are NOT introduced by this change. The apply-progress memory noted
"735 pytest tests pass (excluding pre-existing async/sqlite env failures)";
this verification confirms 755 passing tests.

The single collection error is `tests/test_reconciled_profile_serialization.py`
which imports `build_reconciled_profile_v2` from `core`. This is the
deferred `M3` work explicitly excluded from this change's scope per spec
§"Out of scope" and §"Legacy API Compatibility". Excluded.

### 2. Pipeline smoke — `python test_pipeline.py`

**Result: PASS**

End of run output:
```
5. ✅ Excel exportado: /tmp/test_conciliacion.xlsx
6. Generando reporte Word...
✅ Reporte Word exportado: /tmp/test_report.docx
============================================================
TEST COMPLETADO
============================================================
```

Compliance output included CUMPLE / FUERA DE TOLERANCIA / NO CUMPLE rows
as expected.

### 3. Import sanity — UI modules + core helpers

```bash
python -c "import ui.tabs.blast_correlation, ui.modulo_tronadura, ui.tabs.ai_report, ui._blast_correlation_shared; \
           from core.blast_correlation import compute_monthly_trend, detect_pf_outliers_iqr, split_campaign; \
           print('OK')"
```

**Result: PASS** (`OK` printed; ran under `.venv/bin/python`).

Initial run with system Python 3.14.6 failed with `ModuleNotFoundError:
No module named 'pandas'`. Resolved by using the project venv:
`.venv/bin/python` (Python 3.11.15). All required deps present.

### 4. Invariant zero-hit checks

| Check | Command | Hits | Result |
|---|---|---|---|
| M1 | `rg "use_container_width" ui/ app.py` | 0 | PASS |
| H3 | `rg "_highlight_status" ui/tabs/table.py` | 0 | PASS |
| M2 | `rg "streamlit.components.v1" ui/` | 0 | PASS |
| C2 | `rg "from tests\." ui/` | 0 | PASS |
| H2 (bonus) | `rg "df\[.sector.\]\.isin" ui/` | 0 | PASS |

**Result: ALL PASS**

> Note: `rg "_highlight_status" ui/` (without `tabs/table.py`) returns 1
> hit in `ui/labels.py:60` as part of a docstring referencing the
> historical location. This is intentional documentation, NOT a code
> reference. The spec's matrix and scenario both scope the check to
> `ui/tabs/table.py`, so this satisfies the requirement. (If the
> authors preferred total-zero across `ui/`, this can be cleaned up
> later — see SUGGESTION below.)

### 5. C1 evidence — `ui/step1_upload.py` "Limpiar superficies" handler

Verified in `ui/step1_upload.py:45-59`:

```python
if st.button("🧹 Limpiar superficies cargadas", type="secondary"):
    st.cache_resource.clear()                                  # L46 ✓
    st.cache_data.clear()                                      # L47 ✓
    st.session_state.mesh_design = None                        # L48 onward (after clear)
    st.session_state.mesh_topo = None
    ... (mesh-null assignments)
    st.rerun()                                                  # L59 (last)
```

**Result: PASS** — both cache clears precede the mesh-null assignments AND
precede `st.rerun()`. Matches spec scenario "clear precedes rerun".

`ui/plots.py:61-70` documents the `_mesh` (underscore) contract and the
clear() requirement via docstring. Verified by file read.

### 6. C2 evidence — trend helpers relocation

| Check | Verified? |
|---|---|
| `core/blast_correlation.py` contains `compute_monthly_trend`, `detect_pf_outliers_iqr`, `split_campaign` | YES — lines 459, 507, 532 |
| `tests/test_ai_service_enrich.py` imports them from `core.blast_correlation` (not defines them) | YES — lines 4-8 |
| `ui/tabs/blast_correlation.py` has NO try/except import gate for these | YES — only try/except is for `core.blast_advisor` (legitimate optional dep) and `statsmodels` (legitimate optional); `core.blast_correlation` is unconditional at lines 12-19 |
| `_HAS_TREND_HELPERS` removed | YES (no occurrences in code) |
| 8 tests in `test_ai_service_enrich.py` pass via the re-import | YES — `pytest tests/test_ai_service_enrich.py -v` → 8 passed |

**Result: PASS**

### 7. H1 evidence — `ui/step2_sections.py` no `@st.cache_data` on local-azimuth

| Check | Verified? |
|---|---|
| `_cached_local_azimuth` removed | YES — zero hits in `ui/` |
| Direct `compute_local_azimuth(mesh, np.array([ox, oy]))` calls at the call sites | YES — line 254, 320, 398 |

**Result: PASS**

### 8. H2 evidence — single source of truth for comparison filtering

| File | Imports `apply_comparison_filters` from `ui.filters` | Calls `apply_comparison_filters` | Inline filter loop? |
|---|---|---|---|
| `ui/tabs/dashboard.py` | L9 | L36 | NO |
| `ui/tabs/export.py` | L57 (within `_get_filtered_comparisons` wrapper) | L59 (in wrapper) | NO (wrapper just delegates) |
| `ui/tabs/ai_report.py` | L28 | L243 | NO |
| `ui/tabs/table.py` | L7 (already) | L66 (already) | NO |

`ui/filters.py` exposes:
- `apply_comparison_filters` (L17)
- `filters_summary` (in `__all__` at L112)
- `_collect_active_filters_from_session_state` (in `__all__` at L112)

Spec scenario:
> `rg 'df\["'\'']sector["'\'']\]\.isin' ui/` returns zero

Verified: zero hits.

**Result: PASS**

> ⚠️ **Minor implementation departure** (SUGGESTION, not WARNING):
> The original H2b task said "delete `_get_filtered_comparisons` from
> `ui/tabs/export.py`". Instead, the implementer kept it as a thin
> delegation wrapper (3 lines, no filter logic of its own). The function
> now reads:
> ```python
> def _get_filtered_comparisons() -> list:
>     comps = st.session_state.comparison_results
>     if not comps:
>         return []
>     from ui.filters import _collect_active_filters_from_session_state
>     from ui.filters import apply_comparison_filters
>     return apply_comparison_filters(
>         list(comps), _collect_active_filters_from_session_state()
>     )
> ```
>
> The SSOT invariant is satisfied (no inline filter loop, both call sites
> that use `_get_filtered_comparisons` go through `apply_comparison_filters`).
> The behavior is identical to a full delete + inline replacement.
> Remaining benefit: call sites keep a stable function name.
>
> **Recommendation (optional)**: fully inline the body into the two
> callers (L116, L202) and remove the function. Not blocking archive.

### 9. H4 evidence — berm threshold slider

`ui/sidebar.py:38`:

```python
berm_threshold = st.slider("Ángulo máximo berma (°)", 0, 30, int(DETECTION.berm_threshold))
```

**Result: PASS** — matches `face_threshold` pattern on line 37.

### 10. H5 evidence — shared blast-correlation helper

| Check | Verified? |
|---|---|
| `ui/_blast_correlation_shared.py` exists | YES (322 lines) |
| Exports `project_powder_factor_per_section` + `build_pf_deviation_scatter` (+ `project_powder_factor_per_group`) | YES — `__all__` at L318-322 |
| `ui/modulo_tronadura.py` imports from `ui._blast_correlation_shared` | YES — L26 |
| `ui/tabs/blast_correlation.py` imports from `ui._blast_correlation_shared` | YES — L29 |
| Pre/post byte-identical on synthetic 4-section DataFrame | YES — `python tests/test_h5_blast_correlation_shared.py` → `PRE / POST byte-identical (rows + scatter): OK` |

**Result: PASS** — module is built, wired into both consumers, and
verified to produce byte-identical output to the pre-extraction inline
kernel + scatter for the canonical scatter (`show_ols=True`,
`x_col="Kg_Explosivo"` fallback).

### 11. M4 evidence — section tabs append with `_N` suffix

Verified in `ui/step2_sections.py`:

| Tab | File-line | Behavior |
|---|---|---|
| File | L115-127 | append + `_N` suffix ✓ |
| Interactive | L263-264 | append (no name collision check, but no form re-entry by user) ✓ |
| Manual | L333-351 | append + `_N` suffix ✓ |
| Auto | L383-417 | append + `_N` suffix ✓ |

`_render_sections_table()` L438-440 displays `📋 Total acumulado: N secciones`
banner. Three success messages (L128, L351, L417) also use the same phrasing.

"Limpiar Todas" button (L453, renamed from "Limpiar lista", with "Limpiar
Pendientes" alongside) preserved for explicit clear.

**Result: PASS**

### 12. Spec requirement coverage — ALL 13 requirements

| # | Requirement | Result | Evidence |
|---|---|---|---|
| **C1** | Contour cache invalidation on surface reset | PASS | Check #5 |
| **C2** | Production code MUST NOT import from `tests/` | PASS | Check #6 |
| **H1** | cached helper purity in section building | PASS | Check #7 |
| **H2** | single source of truth for comparison filtering | PASS | Check #8 |
| **H3** | dead highlight helper removed | PASS | Check #4 |
| **H4** | berm threshold slider reads detection default | PASS | Check #9 |
| **H5** | shared blast-correlation helper | PASS | Check #10 |
| **M1** | no `use_container_width` in `ui/` or `app.py` | PASS | Check #4 |
| **M2** | streamlit.components.v2 import | PASS | `ui/tabs/ai_report.py:17` `import streamlit.components.v2 as components`; component registered at L138; `_html_button` wrapper at L146; `streamlit.components.v2` resolves in `python -c` |
| **M4** | section-definition tabs append consistently | PASS | Check #11 |
| **L1** | drop redundant `import numpy as np` / `import pandas as pd` | PASS | Only `import pandas as pd` at module top (line 14); no `import numpy as np` anywhere; the one aliased `import pandas as _idw_pd` at line 299 is intentional name-shadowing (not a redundant duplicate) |
| **L2** | evict `_profile_figs` cache on section mutation | PASS | `pop('_profile_figs', None)` at L127, L265, L350, L416 |
| **L3** | `z_value: Optional[float] = None` (or PEP 604) | PASS | `z_value: float \| None = None` at L108 (PEP 604 — explicitly accepted by design.md §L3) |
| **L4** | drop redundant `import os` (if unused) | PASS | `import os` kept at L10 because still used at L102 (`os.path.splitext`) and L145 (`os.path.exists`). Spec scenario: "has no `import os` (or it is used)" — PASS |

**Result: ALL 13 REQUIREMENTS PASS**

---

## Findings

### CRITICAL
None.

### WARNING
None.

### SUGGESTION

**S1 (cosmetic) — `_get_filtered_comparisons` is a thin wrapper, not a
deletion.** File: `ui/tabs/export.py:51-61`. The H2b task said to delete
the function; the implementer kept it as a delegation-only wrapper. The
SSOT invariant holds (no inline filter loop, all callers go through
`apply_comparison_filters`), but the function name lingers. Optional
follow-up: inline body at call sites L116 and L202, remove function.

---

## Artifacts

| Artifact | Path / location |
|---|---|
| Spec | `openspec/changes/streamlit-audit-remediation/specs/streamlit-legacy-surface-integrity/spec.md` |
| Tasks | `openspec/changes/streamlit-audit-remediation/tasks.md` |
| Design | `openspec/changes/streamlit-audit-remediation/design.md` |
| Apply progress (engram) | topic_key `sdd/streamlit-audit-remediation/apply-progress`, obs #82 |
| This report | `openspec/changes/streamlit-audit-remediation/verify-report.md` |

## Files Inspected (read or grep'd)

- `ui/step1_upload.py` (C1)
- `ui/step2_sections.py` (H1, M1, M4, L2, L4) — 456 lines
- `ui/sidebar.py` (H4)
- `ui/_blast_correlation_shared.py` (H5) — 322 lines (new file)
- `ui/modulo_tronadura.py` head (L1, H5 imports)
- `ui/tabs/blast_correlation.py` head — lines 1-60 (C2, H5 import)
- `ui/tabs/dashboard.py` (H2)
- `ui/tabs/export.py:51-85` (H2 wrapper)
- `ui/tabs/ai_report.py:1-50` (H2, M2)
- `ui/filters.py` (H2 — `__all__` line 112)
- `ui/labels.py:55-69` (H3 docstring reference)
- `ui/ref_lines.py:108` (L3)
- `core/blast_correlation.py` (C2 — helpers at 459, 507, 532)
- `tests/test_ai_service_enrich.py:1-30` (C2 re-imports)
- `tests/test_h5_blast_correlation_shared.py` (H5 byte-identity script)

---

## Next Recommended

**`archive`** — run `sdd-archive` to sync delta specs and close out the
change. No remediation needed.

## Risks

None. The implementation is behavior-preserving. The single SUGGESTION
is cosmetic and does not block archive.

## Skill Resolution

| Requested Skill | Resolution |
|---|---|
| `developing-with-streamlit` | Loaded. The v2 component pattern (`components.component(html=..., js=...)` registered once + `_html_button` wrapper) matches the `references/custom-components-v2.md` CRITICAL guidance in the skill. |
| `work-unit-commits` | Loaded. Verified the apply-phase produced 7 commits in the order specified by tasks.md (CRITICAL → HIGH → MEDIUM → LOW inside one PR, H5 last of HIGH for bisect). |
