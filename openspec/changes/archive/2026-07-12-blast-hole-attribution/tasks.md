# Tasks: blast-hole-attribution

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~332 (330 new + 2 modified) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Domain module + unit tests | PR 1 | Base: main. Unit + math tests ship together. |
| 2 | UI expander + smoke | PR 2 | Base: main. Depends on PR 1; small diff. |

Single-PR is also viable: ~332 lines is under budget and tests ship with code per work-unit-commits.

## Phase 1: Domain Module (core/blast_attribution.py)

- [x] 1.1 Create `core/blast_attribution.py` with public `attribute_holes_to_benches(blast_df, comparison_results, sections, tolerance, top_n=5, min_delta_m=0.5)`.
- [x] 1.2 Add `_resolve_kg_column(blast_df)` with fallbacks `Kilos_Cargados_real → Kilos_Cargados → kg → 1.0` (matches `blast_model.py:572`).
- [x] 1.3 Add `_feature_world_xy(section, bench, feature)` using `bench_real` and `azimuth_to_direction`.
- [x] 1.4 IDW scoring loop: `d² = (feature_xy − hole_xy)²`, mask `d² ≤ tolerance²`, score `kg / max(d², 1e-4)`.
- [x] 1.5 Per-feature top-N selection → `list[dict]` with `{section, bench_num, feature, delta_m, top_holes[], n_candidates}`.
- [x] 1.6 Guard empty inputs (`None` df, missing `X`/`Y`, no MATCH rows, no section match) → return `[]` (never raise).
- [x] 1.7 Leave `core/__init__.py` untouched (Legacy API Compatibility requirement).

## Phase 2: Unit Tests (tests/test_blast_attribution.py)

- [x] 2.1 Create `tests/test_blast_attribution.py` with synthetic 4-hole 30×30 m fixture and MATCH-row builder helper.
- [x] 2.2 `test_empty_blast_df_returns_empty`: empty df → `[]`.
- [x] 2.3 `test_missing_kg_column_uses_fallback`: no `Kilos_*` → 1 kg/hole, output still ranked.
- [x] 2.4 `test_no_deviated_rows_returns_empty`: MATCH rows with `|delta| ≤ 0.5 m` → `[]`.
- [x] 2.5 `test_top_n_limits_results`: 4 eligible, `top_n=2` → exactly 2 entries, highest first.
- [x] 2.6 `test_multi_feature_isolation`: one hole near crest AND toe → appears in both rows, no cross-feature aggregation.
- [x] 2.7 `test_world_xy_azimuth_convention`: section `(0,0,0)` az 0° → North; az 90° → East (per `azimuth_to_direction`).

## Phase 3: UI Integration (ui/tabs/blast_correlation.py)

- [x] 3.1 Add `from core.blast_attribution import attribute_holes_to_benches` near existing core imports.
- [x] 3.2 Inside `tab_bnc` call `attribute_holes_to_benches(blast_df, comparison_results, sections, tolerance)` right after line 339.
- [x] 3.3 Add `_render_attribution_block(results)` after `_render_stemming_crest_block` (~line 988): expander "Atribución por Pozo", per-feature selectbox, dataframe columns `Pozo/Malla/kg/Distancia (m)/Contribución (%)`; `st.info("Sin desviaciones atribuibles")` when empty.
- [x] 3.4 Spanish copy inlined (matches `_render_pasadura_toe_block` / `_render_stemming_crest_block` pattern; no `labels.py` change).

## Phase 4: Verification

- [x] 4.1 `pytest tests/test_blast_attribution.py -v --tb=short` → 6 tests green.
- [x] 4.2 `pytest tests/test_blast_*.py -v --tb=short` → no regression.
- [x] 4.3 `pytest tests/ -v --tb=short --ignore=tests/test_openblast.py` → full suite green.
- [x] 4.4 `python -c "from core.blast_attribution import attribute_holes_to_benches; print(attribute_holes_to_benches(None, [], []))"` → returns `[]` without raising.
- [x] 4.5 Streamlit light smoke on blast-correlation tab with empty `comparison_results` → renderer does not raise.
