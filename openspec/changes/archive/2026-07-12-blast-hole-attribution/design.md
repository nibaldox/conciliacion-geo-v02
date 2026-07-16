# Design: blast-hole-attribution

## Technical Approach

Per-feature hole attribution: for each MATCH row with non-zero `delta_crest` or `delta_toe`, convert along-profile distance to world XY, then run the same IDW-style proximity search used in `compute_energy_density_along_profile` (`core/blast_model.py:506`) to find the top-N contributing wells ranked by `kg / d²`. New module `core/blast_attribution.py`, additive renderer in `ui/tabs/blast_correlation.py`, additive test file. No changes to `core/__init__.py`, no schema changes.

## Architecture Decisions

| Decision | Options | Choice | Why |
|---|---|---|---|
| Coordinate transform | (a) re-derive from scratch; (b) call `azimuth_to_direction` | (b) `azimuth_to_direction(section.azimuth)` | Already canonical, convention `[sin(az), cos(az)]` matches `proyectar_pozos_en_seccion:278` and `_render_energy_density_along_profile:1019` |
| Which feature coords? | (a) `bench_design`; (b) `bench_real` | (b) `bench_real` | "Which hole caused the as-built overbreak?" — measured position is the question, not designed |
| World-vs-section split | (a) restrict to holes already projected via `proyectar_pozos_en_seccion`; (b) search full `blast_df` by collar `(X, Y)` | (b) | The energy function does the same; collar is the canonical hole location. Projection is perpendicular axis, redundant here |
| d² floor | (a) 0; (b) `1e-4` m² | (b) `1e-4` | Avoids div-by-zero; matches `blast_model.py:583` |
| Min deviation filter | (a) attribute all MATCH rows; (b) gate by `|delta| > min_delta_m` | (b) `0.5 m` default | Don't waste cycles on compliant benches; configurable |
| kg fallback | (a) skip row; (b) `1.0` kg/hole | (b) | Matches `blast_model.py:572` fallback convention |
| Output shape | tuple of dataclasses vs `list[dict]` | `list[dict]` | Mirrors `comparison_results`, downstream Streamlit iterates without import gymnastics |
| UI insertion point | (a) new top-level expander; (b) at the end of `tab_bnc` after `_render_stemming_crest_block` | (b) | Where blast-per-bench analyses live; mirrors `_render_pasadura_toe_block`/`_render_stemming_crest_block` pattern |

## Data Flow

    comparison_results (MATCH rows with |delta| > 0.5 m)
            │
            ▼
    attribute_holes_to_benches(blast_df, comparison_results, sections,
                               tolerance=15.0, top_n=5)
            │
            ├─ build {name: SectionLine} dict (O(1) lookup)
            ├─ resolve kg column (Kilos_Cargados_real → ... → 1.0 fallback)
            │
            ▼
    per-feature loop (section, bench_num, feature ∈ {crest, toe}):
        feature_xy = section.origin + azimuth_to_direction(azimuth) * distance
        d² = (feature_x − hole_x)² + (feature_y − hole_y)²         ← broadcast
        mask = d² ≤ tolerance²
        contribution = kg[None,:] / max(d², 1e-4)[None,:]
        take top_n by contribution.sum(per-hole) → rows for that feature
            │
            ▼
    list[dict] → _render_attribution_block → st.dataframe(per deviated feature)

## File Changes

| File | Action | Description |
|---|---|---|
| `core/blast_attribution.py` | Create | `attribute_holes_to_benches()`, `_resolve_kg_column()`, `_feature_world_xy()`, dataclass-free pure functions (~120 LOC) |
| `ui/tabs/blast_correlation.py` | Modify | +1 import line, +1 call inside `tab_bnc` after `_render_stemming_crest_block` (line 339), +`_render_attribution_block` after `_render_stemming_crest_block` (line 988, ~60 LOC) |
| `tests/test_blast_attribution.py` | Create | Five+ tests: empty `blast_df`, missing `Kilos`, no deviated rows, single-feature ranking, multi-feature isolation (~150 LOC) |
| `openspec/changes/blast-hole-attribution/design.md` | Create | This file |

## Interfaces / Contracts

```python
def attribute_holes_to_benches(
    blast_df: pd.DataFrame,
    comparison_results: list[dict],
    sections: list[SectionLine],
    tolerance: float = DEFAULTS.blast_correlation_radius_m,
    top_n: int = 5,
    min_delta_m: float = 0.5,
) -> list[dict]:
    """Return one entry per deviated MATCH feature:
        [{section, bench_num, feature ('crest'|'toe'),
          delta_m, top_holes: [{label_pozo, malla, kg,
                                distance_m, contribution_pct}], n_candidates}]"""
```

Returns `[]` (never raises) on: empty `blast_df`, missing `X`/`Y`, no MATCH rows, no section match, no holes within `tolerance`. Section lookup by `comparison['section']` against `{s.name for s in sections}`.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (5+ tests) | empty `blast_df`, missing `Kilos`, no `delta_*`, single-feature top_n=2 ranking, multi-feature isolation | Synthetic fixture: 4 holes in 30×30 m box, 1 MATCH row at known `(x,y)`; verify sorted contribution and per-feature isolation |
| Unit (math) | world-XY conversion correctness | Build section at `(0,0,0)` azimuth 0° and 90°; assert `(sin·d, cos·d)` matches North=0 and East=90 conventions |
| Integration | All existing `tests/test_blast_*.py` green | `pytest tests/test_blast_*.py -v` |
| Smoke | UI renders without crash on empty `comparison_results` | Streamlit light render with synthetic data |

## Changed-Lines Forecast (400-line budget)

| Path | New | Modified | Deleted |
|---|---|---|---|
| `core/blast_attribution.py` | 120 | 0 | 0 |
| `ui/tabs/blast_correlation.py` | 60 | 2 (1 import, 1 call) | 0 |
| `tests/test_blast_attribution.py` | 150 | 0 | 0 |
| **Total** | **~330** | **2** | **0** |

**Decision needed before apply: No** | **Chained PRs recommended: No** | **400-line budget risk: Low**

## Open Questions

- None blocking. `label_pozo` resolution reuses `find_df_column` over `['label_pozo', 'pozo_id', 'id_pozo', 'numero']` (None silently). `malla` resolution already exists at `blast_correlation.py:110`.
