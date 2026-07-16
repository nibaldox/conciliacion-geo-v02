# Design: streamlit-audit-remediation

## Goals & Non-Goals

**Goals.** Behavior-preserving remediation of 11 audit findings on the maintainer-owned Streamlit surface (`app.py` + `ui/`). The temporary lift of `openspec/config.yaml`'s `ui/` off-limit rule (per proposal §Scope) authorizes these touches for this change only. Legacy `core/__init__.py` stays untouched; three new top-level helpers land additively in `core/blast_correlation.py`.

**Non-Goals.** `M3` (`build_reconciled_profile` → `_v2` migration) — explicitly deferred per proposal. No `web/`, `api/`, `cli.py`, `core/__init__.py` changes beyond the additive C2 imports. No new dependencies.

**Resolved design defaults (orchestrator decisions).**
1. `M4` — append (accumulate) with `_N` suffixing in all 4 section tabs (`file`, `interactive`, `manual`, `auto`).
2. `C1` — `st.cache_resource.clear()` + `st.cache_data.clear()` in the "Limpiar superficies" handler.
3. `H5` — extract shared logic to `ui/_blast_correlation_shared.py` (UI helper, **not** `core/`).

---

## Per-Finding Approach

| # | Finding | File:line | Action |
|---|---|---|---|
| **C1** | Contour cache leaks across clear | `ui/step1_upload.py:45-57` | Insert `st.cache_resource.clear(); st.cache_data.clear()` **before** `st.rerun()`. Document underscore contract on `ui/plots.py:62`. |
| **C2** | Helpers in `tests/` | `ui/tabs/blast_correlation.py:28-36`, `tests/test_ai_service_enrich.py:5-107` | Copy `compute_monthly_trend`, `detect_pf_outliers_iqr`, `split_campaign` verbatim to `core/blast_correlation.py`. Drop `try/except ImportError`. Tests file re-imports from `core.blast_correlation` (signatures preserved exactly). **Inverted arrow**: production no longer depends on tests. |
| **H1** | `cache_data` reads `session_state` | `ui/step2_sections.py:29-31` | **Drop the cache.** `compute_local_azimuth` is cheap (one mesh kNN lookup); the cache added complexity for negligible win. Calls at lines 259, 324 become direct `compute_local_azimuth(mesh_d, np.array([ox, oy]))`. |
| **H2** | 4 inline filter loops | `ui/tabs/dashboard.py:31-38`, `ui/tabs/export.py:51-72`, `ui/tabs/ai_report.py:212-233` | `_get_filtered_comparisons` (export) deleted; callers use `apply_comparison_filters(rows, _collect_active_filters())`. Add `_collect_active_filters_from_session_state() -> dict` to `ui/filters.py` (returns the 4-key dict from `session_state`). `ai_report._apply_table_filters` already delegates to `apply_comparison_filters`; collapse it to call the new helper directly. |
| **H3** | Dead `_highlight_status` | `ui/tabs/table.py:101-113` | Delete function. `highlight_status` import from `ui.labels` at line 24 is the live one. Verified via `rg '_highlight_status' ui/`. |
| **H4** | Hardcoded berm slider | `ui/sidebar.py:38` | One-line edit: `st.slider(..., 0, 30, int(DETECTION.berm_threshold))` (matches face_threshold on line 37). |
| **H5** | Two blast-correlation copies | `ui/modulo_tronadura.py:391-562`, `ui/tabs/blast_correlation.py:384-480` | See **H5 extraction design** below. Net deletion ~200 LOC. |
| **M1** | `use_container_width=True` | 33 sites in `ui/` | Mechanical rename `use_container_width=True` → `width="stretch"` (Streamlit ≥1.57 default). `app.py` audit: zero hits today (no edit needed). |
| **M2** | `streamlit.components.v1` | `ui/tabs/ai_report.py:17, 135` | **v1 is deprecated** (per `references/custom-components-v2.md` §"CRITICAL"). `st.iframe(src=...)` takes a URL/path, **not inline HTML** — it is *not* a drop-in. Replace `components.html(payload, height=42)` with `st.components.v2.component(html=..., js=...)` registered once at module import (signature `(html="<div/>", js="…default export…")`, mount callable `data=..., key=..., height=42`). Wrap in a private `_html_button(html, key)` helper. **No** replace with `st.iframe`. |
| **M4** | Section list replace/append | `ui/step2_sections.py:128, 338, 391` | Append (matches interactive tab at line 268). `_1`/`_2`/… suffixing pattern already in `file` (lines 122-127) is the canonical loop — copy it into `manual` (338) and `auto` (391). `_render_sections_table()` banner updates to "Total acumulado: N secciones". |
| **L1** | Redundant imports | `ui/modulo_tronadura.py:265, 298, 342, 402, 624, 684, 913` | Delete local `import numpy as np` / `import pandas as pd` (already imported at module top). |
| **L2** | `_profile_figs` stale cache | `ui/tabs/profiles.py:81` | In `step2_sections.py` `_apply_section` handlers, after `st.session_state.sections.append(...)`, add `st.session_state.pop('_profile_figs', None)`. Idempotent and safe (cache rebuilds on next render). |
| **L3** | `Optional[float]` 3.10 syntax | `ui/ref_lines.py:108` | `z_value: float | None = None` (PEP 604, matches `pyproject.toml` `requires-python=">=3.10"`; `ui/tabs/blast_correlation.py:811` already uses `dict | None`). |
| **L4** | Redundant `import os` | `ui/step2_sections.py:107` | Delete (line 10 already imports). |

---

## H5 Extraction Design

Both call sites share the per-section kernel: project blast holes → pull `total_kg`/`num_wells` → call `aggregate_powder_factor_by_group`. They differ in **what enrichment rides alongside** and **what scatter gets rendered**.

### `ui/_blast_correlation_shared.py` — public surface

```python
def project_powder_factor_per_section(
    df_filtered: pd.DataFrame,
    sections: list,
    *,
    kg_col: str | None,
    tolerance: float,
    fecha_corte: str | None,
) -> list[dict]:
    """Inner loop kernel. Returns one dict per section with num_wells,
    total_kg, pf_vol_avg_kgm3, pf_area_avg_kgm2, energy_total_mj, n_pf_valid,
    and the projected wells subset (so callers can compute signed deviations
    with the source DataFrame they already have).

    Behavior: identical to today. Both sites use this verbatim.
    """

def build_pf_deviation_scatter(
    df_corr: pd.DataFrame,
    *,
    x_col: str = 'pf_vol_avg_kgm3',
    x_label: str = 'Powder Factor Volumétrico (kg/m³)',
    over_label: str = 'Sobre-excavación',
    under_label: str = 'Deuda/Relleno',
    radius_m: float,
    show_ols: bool = False,
) -> go.Figure:
    """Build the Plotly scatter with separate over/under traces, optional
    OLS trendline on over points only (modulo_tronadura behavior), and the
    zero-line + axis titles. Returns the figure; caller renders with
    st.plotly_chart.
    """
```

### Per-call differences (preserved via parameter or call-site glue)

| Behavior | `modulo_tronadura.py` | `tabs/blast_correlation.py` |
|---|---|---|
| Signed split source | inline pandas split by `delta_crest > 0` | `core.blast_correlation.compute_signed_deviations(...)` |
| Joined with cuts (`a_over`, `a_under`)? | No | Yes (extra columns) |
| OLS trendline on over | **Yes** (visible) | No (Pearson caption only) |
| Fallback x to `total_kg` when PF missing | Yes (via local variable) | Yes (via local variable) |
| Suffix on per-section name | None | section.sector |
| y axis | absolute | con-signo |

**Per-site glue** (kept in each caller, ~10 lines):

- `modulo_tronadura.py` builds a `df_comp_signed → .groupby('section')` to emit `Sobre-excavación_Media_m`/`Deuda/Relleno_Media_m` columns **before** calling the shared projector; then constructs a normalized df with `Kg_Explosivo`, `Pozos_Cercanos`, `PF_Vol_kgm3`, `Energía_MJ`, `Sobre-excavación_Media_m`, `Deuda/Relleno_Media_m`. Calls `build_pf_deviation_scatter(show_ols=True)`. Pearson r computed at call site with `np.corrcoef`, messages via `st.success/info/warning`.

- `tabs/blast_correlation.py` calls the projector, enriches each row with signed deviations (already cached via `_get_or_compute_sections_data`) and cut-area deltas, then renders **per-tab** scatter variants through the same shared builder (one fn, three callers). No OLS.

**Why a UI module, not `core/`.** The renderer wraps Plotly (`go.Figure`) and reads `st.session_state`; pushing it to `core/` would re-introduce the GUI/domain split the audit found. The kernel stays dep-free (only `pandas`, `numpy`, `core.blast_correlation`, `core.calculo_tronadura`); the figure builder imports `plotly.graph_objects`. Both are 100 % unit-testable with synthetic DataFrames.

---

## Data Flow (H5)

```
        ui/modulo_tronadura.py      ui/tabs/blast_correlation.py
                  │                            │
                  │  blast_df, sections,       │  blast_df, sections,
                  │  kg_col, tolerance,        │  df_filtered_comps,
                  │  fecha_corte               │  tolerance, fecha_corte
                  ▼                            ▼
       ui/_blast_correlation_shared.py
       ┌──────────────────────────────────┐
       │  project_powder_factor_per_section│  ◀── pure kernel
       │  build_pf_deviation_scatter       │  ◀── Plotly only
       └──────────────────────────────────┘
                       │
                       ▼
                pd.DataFrame per section
                       │
              ┌────────┴────────┐
              ▼                 ▼
       modulo_tronadura.py    tabs/blast_correlation.py
       (single scatter+OLS    (per-tab sec/banco/malla
        + Pearson r caption)    variants via shared builder)
```

---

## File Changes

| File | Δ | One-liner |
|---|---|---|
| `ui/plots.py` | modify | docstring: `_mesh` underscore + clear() contract (C1) |
| `ui/step1_upload.py` | modify +1 | `cache_resource.clear()` in clear handler (C1) |
| `ui/step2_sections.py` | modify | H1 (drop cache) · M1 · M4 · L4 |
| `ui/sidebar.py` | modify +1 | `DETECTION.berm_threshold` default (H4) |
| `ui/tabs/table.py` | modify | H3 (delete `_highlight_status`) · M1 |
| `ui/tabs/dashboard.py` | modify | H2 (delegate) · M1 |
| `ui/tabs/export.py` | modify −22 | H2 (delete `_get_filtered_comparisons`) · M1 |
| `ui/tabs/ai_report.py` | modify | H2 (delegate) · M2 (v2 component) · M1 |
| `ui/tabs/blast_correlation.py` | modify | C2 (drop tests import) · H5 (shared kernel) · M1 |
| `ui/tabs/profiles.py` | modify | L2 hook into session_state write · M1 |
| `ui/modulo_tronadura.py` | modify −200 | H5 (shared kernel) · L1 · M1 |
| `ui/ref_lines.py` | modify +1 | L3 (PEP 604 type hint) |
| `ui/filters.py` | modify | H2 (add `_collect_active_filters_from_session_state`) |
| `ui/_blast_correlation_shared.py` | **new +130** | H5 (kernel + Plotly scatter builder) |
| `core/blast_correlation.py` | **modify +110** | C2 (verbatim copy of 3 helpers from tests) |
| `tests/test_ai_service_enrich.py` | modify | C2 (re-import from `core.blast_correlation`; assertions untouched) |

## Testing Strategy

| Layer | Scope | Approach |
|---|---|---|
| Unit | existing ~772 tests | `pytest tests/ -v --tb=short` — must remain green; C2 helpers relocate without test edits |
| Unit (regression) | `_collect_active_filters_from_session_state` | manual session-state fixture test; one new test |
| Integration | `python test_pipeline.py` | smoke (synthetic end-to-end) |
| Manual | Streamlit run-through | all 4 steps + tabs at least once; cache clear visible in logs (C1) |

No new heavy tests required: H5's kernel is a pure function with no Streamlit coupling, but follow-up task may add ~3 unit tests.

## Migration / Rollout

**No data migration.** Single-PR rollout; one logical commit per group (C1, C2, H1, H2, H3, H4, H5, M1, M2, M4, L1-4). Backout: revert the commit group. No schema changes; `core/__init__.py` `__all__` unchanged; `core.blast_correlation.__all__` gets +3 entries (new helpers).

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `st.cache_resource.clear()` wipes caches the user expects to survive (e.g., expensive precomputations) | low | Only `mesh_to_contour_data` and `_cached_decimate` are `cache_resource`-bound to mesh identity; both must refresh on swap. Verified via `rg '@st\.cache_resource' ui/`. |
| H5 extraction drops a per-call diff (a per-section log line, an OLS-only path) | medium | Per-call diffs preserved by *parameter* (`show_ols`) and *call-site glue* (signed-split pre-computation stays at caller). Diff-test with synthetic 4-section DataFrame pre/post. |
| M2 `st.components.v2.component(html=…)` differs from `components.v1.html(html=…)` in iframe/height semantics | medium | v2 figure builder returns a `ComponentRenderer` whose `__call__` accepts `height="42px"` and `key=...`. Verified live with Streamlit 1.58 (built-in venv). The wrapper hides the v2 mechanism behind `_html_button(html, key)`. |
| C2 helper signatures drift (e.g., `damage_col` becomes positional) | low | Copy **byte-for-byte**; tests re-import, not re-define. |
| H1 dropped cache re-introduces lag | low | `compute_local_azimuth` is documented cheap; per-section calls ≤ 50 in interactive tab, ≤ 5/sec manual; no perceptible lag. |
| M4 append-everywhere loses user's "reemplazar" mental model | low | Decision per orchestrator; apply-phase banner says "Acumulado: N secciones" so intent is visible. |
| L2 `_profile_figs` eviction on every interaction is too aggressive | low | Hook fires only on `step2_sections` section *write* (apply button), not on every rerun. |

## Open Questions

None blocking. The three design-phase questions in `proposal.md` §Open Questions are **resolved**:
- **M4**: append-everywhere with suffixing ✓
- **C1**: `cache_resource.clear()` blast radius accepted ✓
- **H5**: helper placement = `ui/_blast_correlation_shared.py` (not `core/`) ✓

## Changed-Lines Estimate (Review Workload Forecast)

| Group | Lines (approx) |
|---|---|
| C1 (1 file) | +3 |
| C2 (2 files) | +115 / −2 |
| H1 (1 file) | −8 |
| H2 (4 files) | +5 / −35 |
| H3 (1 file) | −13 |
| H4 (1 file) | 0 (1 edit) |
| H5 (3 files) | +130 / −200 |
| M1 (sed) | ~33 mechanical edits |
| M2 (1 file) | +12 |
| M4 (1 file) | +15 / −10 |
| L1-L4 (4 files) | −20 |
| **Net** | **+260 / −260 ≈ ±0 LOC across 13 modified + 1 new file** |

**Single-PR-friendly.** Comfortably under the 800-line Review Workload Budget. No chained PRs needed. Delivery strategy `ask-already-resolved` (all design-phase decisions answered).

---

## Success Criteria Mapping

- `rg '_mesh' ui/plots.py` — still flags (intentional underscore) ✓
- `rg 'from tests\.' ui/` — 0 hits after C2 ✓
- `rg 'use_container_width' ui/ app.py` — 0 hits after M1 ✓
- `rg 'streamlit\.components\.v1' ui/` — 0 hits after M2 ✓
- `rg 'df\[.sector.\]\.isin' ui/` — 0 hits after H2 ✓
- `ui/sidebar.py:38` reads `int(DETECTION.berm_threshold)` ✓
- `pytest tests/` + `python test_pipeline.py` green ✓
- `core/__init__.py` `__all__` unchanged ✓
