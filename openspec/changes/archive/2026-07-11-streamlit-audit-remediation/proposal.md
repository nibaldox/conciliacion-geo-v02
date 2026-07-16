# Change: streamlit-audit-remediation

> **Status**: proposal
> **Slice**: batch remediation (11 findings, 4 severity tiers)
> **Risk class**: low-to-medium — behavior-preserving on a maintainer-owned surface; one architectural inversion (C2) plus one dependency edge (H5); no `core/` API changes
> **Scope override**: this change **temporarily lifts** the `openspec/config.yaml` `off_limits` rule for `ui/` (and a single `app.py` `use_container_width` touch if present) per explicit maintainer authorization. This is a one-off scope decision, **not** a permanent precedent. Subsequent changes must re-justify any `ui/` access.

## Why

A targeted audit of the Streamlit surface (`app.py` + `ui/`, ~5700 LOC across 21 files) found two correctness defects, four consistency smells, three deprecation drifts, and two mechanical cleanups. The maintainer uses this surface daily, so every fix is **behavior-preserving**: same outputs, same interactions, only internals improve.

Two findings are correctness defects with user-visible impact:

- **C1** — `@st.cache_resource` keyed on `(grid_size,)` only (underscore-prefixed `_mesh` is excluded from hashing). After `Limpiar superficies` + re-upload with the same grid, the contour plot still renders the previous mesh's data. The figure cache guard at `ui/step1_upload.py:202` already rebuilds the figure; the leak is in the underlying `mesh_to_contour_data`.
- **C2** — `ui/tabs/blast_correlation.py:28-36` imports trend/outlier/campaign helpers from `tests/test_ai_service_enrich`. Production code depending on test modules silently disables the temporal analysis if pytest is reorganized.

The remaining findings are consistency (H1–H5), deprecation (M1–M2), an already-deferred migration (M3, see "Out of scope"), a UX inconsistency (M4), and four mechanical items (L1–L4). Prior fixes that this proposal explicitly **does not re-touch**: `step4_results.py` fragment routing, `_get_profile_pair` mesh re-cut cache, tolerance-slider debounce.

## Scope

### In scope

| Finding | File(s) | Action |
|---|---|---|
| C1 | `ui/plots.py:62`, `ui/step1_upload.py:45-57` | `st.cache_resource.clear()` in the "Limpiar superficies" handler; OR migrate to a session_state-keyed figure cache mirroring the 3D fragment pattern |
| C2 | `ui/tabs/blast_correlation.py:28-36`, `tests/test_ai_service_enrich.py` | Move `compute_monthly_trend`, `detect_pf_outliers_iqr`, `split_campaign` to `core/blast_correlation.py`; invert import arrow |
| H1 | `ui/step2_sections.py:29-31` | Replace cached body with a pure function or pass the mesh via `cache_resource` with the mesh identity key |
| H2 | `ui/tabs/dashboard.py`, `ui/tabs/export.py`, `ui/tabs/ai_report.py` | Replace 4 inline filter loops with `apply_comparison_filters` + `filters_summary` from `ui/filters.py` (table.py already delegates ✓) |
| H3 | `ui/tabs/table.py:101-113` | Delete dead `_highlight_status`; keep `highlight_status` import from `ui.labels` |
| H4 | `ui/sidebar.py:38` | `st.slider("...", 0, 30, int(DETECTION.berm_threshold))` — align with `face_threshold` pattern on line 37 |
| H5 | `ui/modulo_tronadura.py:365-562`, `ui/tabs/blast_correlation.py:47-382` | Extract per-section well projection + powder-factor correlation into `ui/_blast_correlation_shared.py` (new); both modules import the shared helper |
| M1 | `ui/**` (33 call sites) | `use_container_width=True` → `width="stretch"` (Streamlit >=1.57 default already) |
| M2 | `ui/tabs/ai_report.py:17` | `streamlit.components.v1` → `st.components.v2` import path |
| M4 | `ui/step2_sections.py:128, 338, 391` | Pick ONE behavior for "load sections" (replace vs append); see Open Questions |
| L1–L4 | `ui/modulo_tronadura.py`, `ui/tabs/profiles.py:81`, `ui/ref_lines.py:108`, `ui/step2_sections.py:107` | Remove redundant imports; evict `_profile_figs` cache when sections reload; fix `Optional[float]` type hint |

### Out of scope (explicit)

- **M3 — `build_reconciled_profile` → `build_reconciled_profile_v2` migration** (`ui/step3_analysis.py:11,80,82`, `ui/tabs/export.py:12,415,422`). **Deferred** to its own change. v2 returns a `ReconciledProfile` object; every callsite would change from tuple unpacking to attribute access. The capability is already shipped (`openspec/specs/reconciled-profile-serialization/`), the legacy export stays for one more cycle, and migrating UI consumers carries the highest per-callsite risk in this batch. Schedule a focused follow-up.
- `web/`, `api/`, `cli.py` — untouched.
- `core/` — touched only inside `core/blast_correlation.py` to receive the three moved helpers (additive, no signature changes).
- `app.py` (root) — untouched. If a `use_container_width` arg lives here, the apply phase will fix it as part of M1 (mechanical, single sed).
- Already-fixed items: `step4_results.py` fragments, `_get_profile_pair` re-cut cache, tolerance-slider debounce.
- The blast correlation **core logic** in `core/blast_correlation.py` (only the duplication/deps are addressed).
- Permanent lifting of the `ui/` off-limits rule.

## Capabilities

> Contract between proposal and `sdd-spec`. Only `openspec/specs/reconciled-profile-serialization/` exists today (verified). All other surfaces are new.

### New Capabilities

- `streamlit-legacy-surface-integrity` — guarantees for the maintainer-owned Streamlit surface: (a) `mesh_to_contour_data` cache invalidates on `Limpiar superficies`; (b) blast-trend helpers resolve from `core/` (never `tests/`) at import time; (c) `ui/filters.apply_comparison_filters` is the single filter entrypoint (4 sites delegate, 0 inline reimplementations); (d) `berm_threshold` slider reads `DETECTION.berm_threshold`; (e) the powder-factor correlation logic exists in exactly one place (`ui/_blast_correlation_shared.py`); (f) `use_container_width` and `streamlit.components.v1` are absent from `ui/`.

### Modified Capabilities

- None. `core/blast_correlation.py` only gains three top-level functions; its public signature is additive. The `reconciled-profile-serialization` capability is not touched (M3 deferred).

## Approach (per fix, for `sdd-apply`)

1. **C1** — In `ui/step1_upload.py:45-57`, before `st.rerun()`, call `st.cache_resource.clear()` (covers `mesh_to_contour_data`). Alternative if clear() is too broad: refactor to a `st.session_state['contour_cache']` dict keyed on `(id(mesh), grid_size)`, matching the 3D figure pattern at `ui/step1_upload.py:202`.
2. **C2** — Move the three helpers from `tests/test_ai_service_enrich.py` to `core/blast_correlation.py` (no new module). Update `tests/test_ai_service_enrich.py` to import them from the new home. Remove the `try/except ImportError` guard in `ui/tabs/blast_correlation.py:28-36`; import unconditionally.
3. **H1** — Change `_cached_local_azimuth(ox, oy, mesh_id)` in `ui/step2_sections.py` to either (a) take the mesh itself and rely on `cache_resource` with a wrapper that hashes by `id()`, or (b) drop caching and call `compute_local_azimuth(...)` directly — the function is cheap.
4. **H2** — Replace inline filter logic at the 3 offending sites with `apply_comparison_filters(rows, _collect_active_filters())` + `filters_summary(...)`. The existing `table.py:64-69` is the template.
5. **H3** — Delete `ui/tabs/table.py:101-113`. Verify no caller (use `rg '_highlight_status' ui/`); only table.py's local definition exists.
6. **H4** — One-line edit at `ui/sidebar.py:38`: `st.slider("Ángulo máximo berma (°)", 0, 30, int(DETECTION.berm_threshold))`.
7. **H5** — New module `ui/_blast_correlation_shared.py` exposing `project_section_with_powder_factor(profile_design, profile_topo, blasts, polygon) -> pd.DataFrame` and `build_pf_damage_scatter(df, ...) -> plotly.Figure`. Both `modulo_tronadura.py` and `tabs/blast_correlation.py` call the shared functions. Net deletion: ~200 LOC.
8. **M1** — Mechanical: `sed`-equivalent in 33 sites. Confirm via `rg 'use_container_width' ui/ | wc -l` == 0 after.
9. **M2** — Change `import streamlit.components.v1 as components` → `import streamlit.components.v2 as components` in `ui/tabs/ai_report.py:17`; verify any `components.html(...)` / `components.iframe(...)` calls survive the v2 API (signature differs in `st.components.v2`).
10. **M4** — Defer the behavioral decision to the design phase; see Open Questions.
11. **L1–L4** — Mechanical deletions and a one-line `Optional[float]` fix.

## Files affected

| Path | Δ | One-liner |
|---|---|---|
| `ui/plots.py` | modify | (C1) document `_mesh` underscore + clear() contract |
| `ui/step1_upload.py` | modify | (C1) `st.cache_resource.clear()` in clear handler |
| `ui/tabs/blast_correlation.py` | modify | (C2, H5, M1, M2-via-shared) replace tests/ import, delegate to shared, drop `use_container_width` |
| `tests/test_ai_service_enrich.py` | modify | (C2) re-export helpers from `core.blast_correlation`; tests still pass |
| `core/blast_correlation.py` | modify (additive) | (C2) gain 3 helpers; no signature churn |
| `ui/step2_sections.py` | modify | (H1, M1, M4, L4) drop session_state inside cached body, replace `use_container_width`, decide replace-vs-append, drop redundant `import os` |
| `ui/tabs/dashboard.py` | modify | (H2, M1) delegate to `apply_comparison_filters` |
| `ui/tabs/export.py` | modify | (H2, M1) delegate; remove `_get_filtered_comparisons` |
| `ui/tabs/ai_report.py` | modify | (H2, M1, M2) delegate; swap to `st.components.v2` |
| `ui/tabs/table.py` | modify | (H3, M1) delete dead `_highlight_status` |
| `ui/sidebar.py` | modify | (H4) read `DETECTION.berm_threshold` |
| `ui/modulo_tronadura.py` | modify | (H5, L1, M1) delegate correlation to shared; remove 5 redundant `import numpy/pandas` |
| `ui/tabs/profiles.py` | modify | (L2, M1) evict `_profile_figs` on reload |
| `ui/ref_lines.py` | modify | (L3) `z_value: Optional[float] = None` |
| `ui/_blast_correlation_shared.py` | new | (H5) shared powder-factor correlation helpers |
| `openspec/specs/streamlit-legacy-surface-integrity/spec.md` | new (downstream) | created by `sdd-spec` |
| `app.py` | modify (conditional) | (M1) only if `rg 'use_container_width' app.py` returns hits |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `st.cache_resource.clear()` wipes caches the user expects to survive mesh swap (e.g., expensive precomputations) | low | The only `cache_resource` users in `ui/` are `mesh_to_contour_data` and the 3D figure helper; both are mesh-bound and must refresh on swap. Verified via `rg '@st\.cache_resource' ui/` |
| Moving `compute_monthly_trend` etc. to `core/` changes the function signature subtly (numpy dtypes, copy semantics) | low | The functions are pure; copy them verbatim. The test file at `tests/test_ai_service_enrich.py` already imports them — keep its assertions identical. |
| H5 extraction drops a behavior (e.g., a per-section log line) that one copy had but the other didn't | medium | Diff the two implementations carefully in the design phase; surface deltas to the maintainer before refactoring. |
| M2 `st.components.v2` migration changes the iframe/html signature | medium | Read `st.components.v2.component(...)` reference in the design phase; if signatures diverge, keep v1 import for the one callsite and file a follow-up. |
| M4 wrong UX choice (replace vs append) breaks the maintainer's daily workflow | medium | M4 is **explicitly deferred to the design phase** for a maintainer decision. See Open Questions. |
| Scope-override (`ui/` off-limits lift) sets precedent for future changes | low | The proposal explicitly states this is one-off. Subsequent `ui/` touches must re-justify in their own proposal. |

## Rollback plan

Revert in one commit per logical group (cache, deps, filter SSOT, blast dedup, mechanical). No data migrations; no schema changes; no public API surface changes outside `core/blast_correlation.py` gaining three new top-level functions (additive). `pytest tests/ -v --tb=short` and `python test_pipeline.py` are the smoke gates.

## Success criteria

- [ ] `rg '_mesh' ui/plots.py` still flags `_mesh` (underscore is intentional; `@st.cache_resource` skips hashing) — the cache invalidation is now explicit, not implicit.
- [ ] `rg 'from tests\.' ui/` returns zero hits.
- [ ] `rg 'use_container_width' ui/ app.py` returns zero hits.
- [ ] `rg 'streamlit\.components\.v1' ui/` returns zero hits.
- [ ] `ui/filters.py` is the only module defining comparison filter loops (verified via `rg 'df\[.sector.\]\.isin' ui/` == 0).
- [ ] `ui/sidebar.py:38` slider default equals `DETECTION.berm_threshold` (run `python -c "from core.config import DETECTION; assert int(DETECTION.berm_threshold) >= 0"`).
- [ ] `pytest tests/ -v --tb=short` passes (existing ~772 tests + any new ones for C2/H5).
- [ ] `python test_pipeline.py` passes.
- [ ] No file in `core/__init__.py` `__all__` changes.

## Open questions (decision round for maintainer)

These three calls change observable behavior; the orchestrator will surface them before `sdd-design` finalizes.

1. **M4 — replace vs append in `step2_sections.py`**: manual tab (line 338) and auto tab (line 391) **replace** the existing section list; file tab (line 128) and interactive tab **append**. Pick one behavior: (a) replace everywhere (predictable, matches `Limpiar superficies` semantics), (b) append everywhere (preserves manual section additions across auto generations), (c) explicit "Reemplazar / Agregar" radio per tab.
2. **C1 — `cache_resource.clear()` blast radius**: `st.cache_resource.clear()` clears **all** resource caches (3D figure, contour, anything else added later). Acceptable, or prefer the per-key session_state migration (mirrors `ui/step1_upload.py:202`)?
3. **H5 — shared helper placement**: `ui/_blast_correlation_shared.py` (UI-only, smallest blast radius) OR `core/blast_correlation.py` (also consumable by `api/routers/process.py` and any future React surface)? The maintainer's daily use is the UI; core would future-proof the API but expands the change scope to two interfaces.

## Links

- Audit findings: orchestrator-provided input (11 findings, severity-tiered).
- `openspec/specs/reconciled-profile-serialization/spec.md` — sibling capability, untouched by this change.
- `openspec/changes/archive/2026-07-10-reconciled-profile-v2-default/` — prior slice that shipped v2 builder; the v2 import surface this change's M3 would consume is already in place.
- `openspec/config.yaml` — `off_limits` rule for `ui/`, temporarily lifted by this change.
- `AGENTS.md` — import rules (`from core import ...` vs submodule), detection defaults (`DETECTION.berm_threshold=20°`), `core/__init__.py` re-export contract.