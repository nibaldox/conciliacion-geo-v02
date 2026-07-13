# Change: blast-hole-attribution

> **Status**: proposal | **Risk**: additive, low | **Scope override**: temporarily lifts `ui/` off-limits (precedent: `2026-07-12-blast-design-achievement`); blast tab only.

## Why

Pipeline projects holes onto sections and sums PF per section (`core/blast_correlation:364`). Engineers ask **"which hole caused the overbreak on bench 5's crest?"** — no answer today. We have per-section PF and per-bench deviations but no **holes × features** attribution. Dual weighting `kg / d^2` from `compute_energy_density_along_profile` (`core/blast_model.py:506`) is the natural fit.

## Scope

**In**: new `core/blast_attribution.py` with `attribute_holes_to_benches(blast_df, comparison_results, sections, tolerance, top_n=5)`. Renderer `_render_attribution_block` in `ui/tabs/blast_correlation.py`. New `tests/test_blast_attribution.py` (≥5 tests).

**Out**: Gaps 0/3/4 (separate). PF/energy density/malla/pasadura/stemming-crest renderers unchanged. `web/`, `api/`, `cli.py`, `app.py`, other `ui/*` untouched. Permanent `ui/` lift — not granted.

## Capabilities

**New** — `blast-hole-attribution`: (a) per-feature hole attribution within `tolerance` of the feature's world position; (b) ranking by `kg / d^2`; (c) graceful empty/missing-data; (d) existing blast analysis unchanged.

**Modified**: None.

## Approach

**Core** — `attribute_holes_to_benches(blast_df, comparison_results, sections, tolerance=15.0, top_n=5)`:

1. Iterate MATCH rows where `delta_crest` or `delta_toe` is non-zero.
2. Resolve section by `comparison.section` → `sections[i]`.
3. Convert crest/toe along-profile distance to world XY: `world_xy = section.origin + azimuth_to_direction(section.azimuth) * distance`. Use `bench_real` (measured) coords.
4. Mask blast holes whose collar `(X, Y)` is within `tolerance` m horizontal of the crest OR toe. Same shape as `compute_energy_density_along_profile:577-587`.
5. Rank by `kg / d^2` — IDW × charge, identical to `core/blast_model.compute_energy_density_along_profile:583-587`. Cap at `top_n`.
6. Return `[{section, bench_num, feature, delta_m, top_holes: [{label, malla, kg, distance_m, contribution_pct}]}]`.

Empty `blast_df`, missing `X`/`Y`/`Kilos`, no deviated rows → `[]`. Never raises.

**UI** (`ui/tabs/blast_correlation.py`) — `_render_attribution_block` after `_render_stemming_crest_block` (line 988). `st.expander` with deviated-bench dropdown + ranked-holes table. Spanish strings, mirrors `_render_stemming_crest_block` pattern.

## Affected Areas

| Path | Δ |
|---|---|
| `core/blast_attribution.py` | new (~120 LOC) |
| `ui/tabs/blast_correlation.py` | +renderer (~60 LOC, scope override) |
| `tests/test_blast_attribution.py` | new (~150 LOC, ≥5 tests) |
| `openspec/specs/blast-hole-attribution/spec.md` | new (sdd-spec) |
| `openspec/changes/ACTIVE.md` | append row |

## Risks

| Risk | Mit |
|---|---|
| `ui/` edit rejected | Orchestrator authorization precedent (`2026-07-12-blast-design-achievement`). Blast-tab-only, additive. |
| World-coord conversion off | Reuse `azimuth_to_direction` (`core/section_cutter.py:32`); unit-test the math. |
| `Kilos` missing | Fall back to 1 kg/hole (same as `compute_energy_density_along_profile:572`). |
| Tolerance wrong | Default = `DEFAULTS.blast_correlation_radius_m` (15 m); UI-tunable. |
| Cross-feature double-counting | Each hole listed once per (section, bench, feature); no aggregation. |

## Rollback

Revert PR (1 new module + 1 new test file + 1 renderer block). No DB/schema/flags. All existing renderers unchanged.

## Dependencies

`core.section_cutter.azimuth_to_direction:32`, `proyectar_pozos_en_seccion` (reference pattern), `DEFAULTS.blast_correlation_radius_m` (default tolerance).

## Success Criteria

- [ ] `attribute_holes_to_benches` returns top_n ranked holes per deviated feature, ranked by `kg / d^2`.
- [ ] `_render_attribution_block` renders Spanish strings, no crash on empty inputs.
- [ ] All existing blast tests pass (`pytest tests/test_blast_*.py -v`).
- [ ] ≥5 new tests pass: empty blast_df, missing Kilos, no deviated rows, single-feature ranking, multi-feature isolation.
- [ ] `core/__init__.py` diff is empty.

## Forecast (400-line budget)

`core/blast_attribution.py` ~120 + UI ~60 + tests ~150 ≈ **~330 LOC**. Single PR, no chaining.