# Change: blast-drill-compliance

> **Status**: proposal | **Risk**: additive, medium | **Scope override**: temporarily lifts `ui/` off-limits for `ui/modulo_tronadura.py` (blast module uploader only) per explicit user authorization (precedent: `2026-07-12-blast-design-achievement`).

## Why

`core/calculo_tronadura.py:165 procesar_pozos` ingests **as-drilled** reports but never compares them to the **planned blast design**. Drill deviation (collar offset, inclination error, azimuth drift, length, charge) is the documented #1 predictor of overbreak — predictive before topo confirms damage. Gap 3.

## Scope

**In**: new `core/drill_compliance.py` exposing `compute_drill_compliance(design_df, actual_df, match_by="label")`; optional uploader in `ui/modulo_tronadura.py` ("Cargar Diseño de Voladura (CSV)") next to `blast_file` (line 47); `_render_drill_compliance_block` (Spanish); `tests/test_drill_compliance.py`.

**Out**: Gap 4 (predictive overbreak — separate). Gaps 0/1/2/5 closed. M3/stability. No permanent lift of `ui/`.

## Capabilities

**New** — `blast-drill-compliance`: (a) match design↔actual by `label` or nearest-neighbor; (b) per-hole ΔX, ΔY, ΔZ_collar, Δincl, Δazimuth, Δlength, Δkg; (c) mean|Δ| per dim, optionally by `malla`/`sector`; (d) compliance score = % holes within tolerance; (e) graceful empty design file.

**Modified**: None.

## Approach

`compute_drill_compliance(design_df, actual_df, match_by="label", tolerances=None, group_by=None)` → `{per_hole, aggregates, compliance_score, per_group}`. `match_by="label"` joins on `Pozo` reused by `procesar_pozos`. `match_by="nearest"` falls back to `scipy.spatial.cKDTree` on (X, Y) within 5 m (mirrors `match_threshold`). Per-hole Δ via numpy; aggregates via `groupby().agg(mean_abs_delta)`. Compliance = `(abs(Δ) <= tol).mean()` per dim → 0–1. Tolerances: new frozen `DrillComplianceDefaults` in `core/config.py` (`ΔX=0.5m, ΔY=0.5m, ΔZ=0.3m, Δincl=3°, Δaz=5°, Δlen=0.5m, Δkg=10%`). Not re-exported from `core/__init__.py`.

UI: new uploader below line 51; absent → `st.info("Sin diseño cargado — omitiendo verificación")`; present → `st.expander("🎯 Cumplimiento de Perforación")` with `st.dataframe(per_hole)` + per-dim `st.metric`. Existing `procesar_pozos` flow untouched.

## Affected Areas

| Path | Δ |
|---|---|
| `core/drill_compliance.py` | new (~120 LOC) |
| `core/config.py` | +`DrillComplianceDefaults` |
| `tests/test_drill_compliance.py` | new (~6 tests) |
| `ui/modulo_tronadura.py` | +uploader + expander (override) |
| `openspec/specs/blast-drill-compliance/spec.md` | new |
| `openspec/changes/ACTIVE.md` | append row |

## Risks

| Risk | Mit |
|---|---|
| `ui/` edit rejected | User authorization + blast-module-only |
| No label col in design | Auto-fallback to nearest-neighbor |
| Mis-pair >5 m | Drop + warn; never mis-attribute |
| `core/__init__.py` drift | Not re-exported |
| Tolerance disagreement | Module-level constants, tunable |

## Rollback

Revert PR (1 new module, 1 modified config, 1 modified UI, 1 new test). No schema/flags.

## Dependencies

`scipy.spatial.cKDTree` (already in `core/blast_attribution.py`), `pandas`, `numpy`. Optional `malla`.

## Success Criteria

- [ ] Returns per-hole Δ + aggregate score for matching labels.
- [ ] Nearest-neighbor fallback; no raise on empty/None.
- [ ] Uploader optional; app unchanged without design file.
- [ ] Spanish expander shows per-hole table + per-dim metric.
- [ ] `pytest tests/test_drill_compliance.py` ≥6 new tests pass.

## Forecast (400-line budget)

~120 + ~15 + ~140 + ~50 = **~325 LOC**. Single PR.
