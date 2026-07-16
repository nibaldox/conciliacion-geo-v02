# Design: blast-design-achievement

## Technical Approach

Two additive pure-Python helpers + one tiny Streamlit wiring block. Both helpers are pure functions (no Streamlit, no Plotly) so they are unit-testable in isolation. The legacy UI block mirrors an existing one line-for-line. All outputs feed off data the pipeline already produces — no new sensors, no schema changes.

- **Gap 2** — `compute_stemming_crest_correlation` is a structural twin of `compute_pasadura_toe_correlation` (`core/blast_model.py:172`). Same return shape (`{per_bench, per_bench_other, r, p_value, n_benches, interpretation}`), same guards, same lazy `scipy.stats.pearsonr` pattern.
- **Gap 5** — new `core/blast_achievement.py` (mirrors `core/blast_advisor.py`'s structure: pure helpers + Spanish-neutral dict outputs + `__all__`). Three-tier partial credit scoring with weights 0.4 / 0.3 / 0.3.
- **UI** — `_render_stemming_crest_block` is a copy-with-replace of `_render_pasadura_toe_block` (`ui/tabs/blast_correlation.py:864-903`). Per-malla table at lines 342-355 gains one column. Global score renders as a `st.metric` above the dataframe.

## Architecture Decisions

### Decision: Stemming column auto-detection

**Choice**: Reuse the existing `_TACO_CANDIDATES = ("Taco_m", "Taco", "Stemming")` from `core/blast_metrics.py:37` via `core.column_utils.first_present_column(blast_df, _TACO_CANDIDATES)`. Same pattern as `kilos_column()` at `core/column_utils.py:33`.
**Alternatives considered**: Hardcode `Taco_m`. — Rejected because `core/blast_metrics.py:382-394` already promotes a candidate list for stemming_ratio and other modules handle ENAEX/Vulcan export variants.
**Rationale**: Single source of truth for column resolution. Already used by `enrich_blast_dataframe`. `ui/modulo_tronadura.py:592-593` confirms `Taco_m` is the canonical post-processed name.

### Decision: Crest/toe tolerance for achievement scoring

**Choice**: Derive `crest_status`/`toe_status` inside the function from `|delta_crest|` / `|delta_toe|` vs. `TOLERANCES.bench_height["pos"]` (1.5 m default). Function accepts optional `crest_tolerance_m` and `toe_tolerance_m` overrides.
**Alternatives considered**: Reuse `height_status` from each MATCH row. — Rejected because `height_status` is for vertical `bench_height` deviation, NOT for horizontal crest/toe position. `core/profile_compliance.py:179-198` confirms they are independent deviations.
**Rationale**: 1.5 m matches the bench-height positive tolerance — a defensible horizontal proxy. Override knob lets ops teams tune per-site without code changes. Tests inject 0.5 m / 3.0 m to cover both tight and loose sites.

### Decision: Per-malla → comparison-row join

**Choice**: Reuse the join logic in `_compute_malla_correlation` (`ui/tabs/blast_correlation.py:580-667`). For each `malla`:
1. Filter blast holes: `blast_df[blast_df[malla_col] == malla]`.
2. Project each section with `proyectar_pozos_en_seccion` → `intersected_sections`.
3. Filter comparisons: `df_comps[df_comps["section"].isin(intersected_sections)]`.
4. Compute achievement score across those rows.

The new `compute_design_achievement_score` operates on already-filtered comparisons; the caller does the malla-to-section mapping. This keeps the score helper free of Streamlit/plotly concerns.
**Rationale**: Matches the existing `_compute_malla_correlation` contract (same join, same `intersected_sections` derivation). No new blast-projection code.

### Decision: Where to insert UI blocks

**Choice**:
- `_render_stemming_crest_block` invoked at line 904, immediately after `_render_pasadura_toe_block(blast_df, comparison_results)` at line 330 (inside `tab_bnc`). Same Spanish strings, same `st.metric` layout, same warning/info copy.
- `Logro Diseño (%)` column appended to `col_list_m` (line 342) and `display_map_m` (line 344) inside `tab_mal`. Score column appears AFTER `energy_total_mj` so existing columns stay untouched.
- Global score: `st.metric("Logro Diseño Global", ...)` rendered above `st.dataframe(df_m_disp)` at line 357.

**Rationale**: Mirrors the pasadura wiring exactly (additive, no reordering). The scope override from the proposal authorises blast-tab-only edits inside `ui/`.

## Data Flow

```
session_state.blast_df_clean
        │
        ▼
core.blast_metrics.enrich_blast_dataframe  ──► Taco_m canonical
        │  (already invoked in compute_powder_factor)
        ▼
core.blast_model.compute_stemming_crest_correlation
        │  groupby (Z_collar - 15.0).round(0) → mean Taco_m
        │  groupby level from comparison_results → mean delta_crest
        │  Pearson r between paired per-bench series
        ▼
ui.tabs.blast_correlation._render_stemming_crest_block
        │  → st.metric + st.dataframe + warning (Spanish)

session_state.comparison_results  ──► MATCH rows w/ height_status/angle_status/berm_status/delta_crest/delta_toe
        │
        ▼
core.blast_achievement.compute_design_achievement_score
        │  per row: derive crest_status/toe_status from |delta| vs tol
        │  per row: score = 0.4·crest + 0.3·toe + 0.3·berm
        │  per-malla groupby via section-name join
        ▼
ui.tabs.blast_correlation._compute_malla_correlation  ──► df_malla_corr + df_malla_corr["score_pct"]
        ▼
tab_mal: st.metric global + st.dataframe with Logro Diseño (%) column
```

## File Changes

| File | Action | Description |
|---|---|---|
| `core/blast_model.py` | Modify | Add `compute_stemming_crest_correlation` (~75 LOC, after line 329). Import `_TACO_CANDIDATES` from `core/blast_metrics`; use `first_present_column`. |
| `core/blast_achievement.py` | Create | New module. Constants `_W_CREST/_W_TOE/_W_BERM`, helper `_row_credit(status)`, main `compute_design_achievement_score`. ~90 LOC. |
| `tests/test_blast_model.py` | Create | 4 tests mirroring pasadura tests at `tests/test_blast_correlation.py:426-474` (basic/no-data/one-bench/missing-cols). ~85 LOC. |
| `tests/test_blast_achievement.py` | Create | 4 tests: per-malla score, global score, FUERA partial credit 0.5, missing malla column. ~75 LOC. |
| `ui/tabs/blast_correlation.py` | Modify | Import the two new functions (lines 20-25); append `score_pct` to `col_list_m` (line 342) + `display_map_m` (line 344); add `_render_stemming_crest_block` (mirrors lines 864-903); invoke at line 904; `st.metric` global above line 357. ~50 LOC. |
| `openspec/changes/ACTIVE.md` | Modify | Append one row. |

## Interfaces / Contracts

```python
# core/blast_model.py
def compute_stemming_crest_correlation(
    blast_df: pd.DataFrame,
    comparisons: list[dict],
    bench_height: float = 15.0,
    taco_column: str | None = None,
) -> dict:
    """Pearson r between mean Taco_m per floor and mean delta_crest per level."""
    # Returns: {taco_per_bench, crest_per_bench, r, p_value, n_benches, interpretation}
```

```python
# core/blast_achievement.py
W_CREST, W_TOE, W_BERM = 0.4, 0.3, 0.3
PARTIAL_CREDIT = {STATUS_CUMPLE: 1.0, STATUS_FUERA: 0.5}

def compute_design_achievement_score(
    comparisons: list[dict],
    malla_to_section: dict[str, list[str]] | None = None,
    crest_tolerance_m: float | None = None,
    toe_tolerance_m: float | None = None,
) -> dict:
    """Three-tier weighted score. Returns {global, breakdown, per_malla,
    n_total, n_passing_crest/toe/berm}."""
```

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (test_blast_model.py) | `compute_stemming_crest_correlation`: positive r, negative r, zero variance, missing Taco_m, single bench, empty inputs | Synthetic DataFrames + mock comparison rows; assert `r`, `n_benches`, `interpretation` substrings. |
| Unit (test_blast_achievement.py) | Score weights (sum=1.0), partial credit 0.5/1.0/0.0, per-malla grouping by section join, global score when no malla column | Inject MATCH rows with known status mix; assert percentages. |
| Integration | Pasadura block still renders, PF→damage regression unchanged | Re-run `pytest tests/test_blast_correlation.py tests/test_blast_integration.py`. |
| UI smoke | `_render_stemming_crest_block` no-crash + score column appears | Manual `streamlit run app.py` blast tab. Not in CI (matches AGENTS.md). |

## Migration / Rollout

No migration. Single PR. Additive only:
- Existing `compare_design_vs_asbuilt` rows untouched.
- Existing pasadura/PF renderers untouched.
- New functions importable from `core.blast_model` / `core.blast_achievement` (NOT re-exported from `core/__init__.py`, per AGENTS.md import rules).
- Tolerance defaults pull from `TOLERANCES.bench_height["pos"]` — no new constants in `core/config.py`.

## Open Questions

- [ ] Should `crest_tolerance_m` also default to `TOLERANCES.face_angle["pos"]` (5°) as a secondary knob when horizontal position scales with face angle? Defer to sdd-spec.
- [ ] Confirm `malla_to_section` join logic is identical when user filters by sector/malla before rendering. Verified via inspection of `_compute_malla_correlation`; flag in sdd-spec for review.

## Changed-Lines Estimate

| Area | LOC |
|---|---|
| `core/blast_model.py` (+stemming fn, imports) | ~80 |
| `core/blast_achievement.py` (new) | ~95 |
| `tests/test_blast_model.py` (new) | ~85 |
| `tests/test_blast_achievement.py` (new) | ~75 |
| `ui/tabs/blast_correlation.py` (renderer + column + metric) | ~50 |
| `openspec/changes/ACTIVE.md` | ~1 |
| **Total** | **~386** |

Under the 400-line budget. No chaining required.