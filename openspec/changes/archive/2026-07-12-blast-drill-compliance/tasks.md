# Tasks: Blast Drill Compliance

## Review Workload Forecast

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Low
Changed lines: ~386 (single PR)

## Phase 1: Foundation

- [x] 1.1 Add frozen `DrillComplianceDefaults` (8 fields) + `DRILL_COMPLIANCE` singleton in `core/config.py` after line 250 (`SectorDeviationDefaults`)
- [x] 1.2 Create `core/drill_compliance.py` — imports: pandas, numpy, `scipy.spatial.cKDTree`, `find_df_column`, `DRILL_COMPLIANCE`
- [x] 1.3 Add `_DRILL_COL_ALIASES` (Pozo, X, Y, Z_collar, Incl, Az, Len, Kilos) mirroring `_TACO_CANDIDATES`
- [x] 1.4 Add `_resolve_columns(df, required)` via `find_df_column(..., raise_error=required)`; missing optional → NaN

## Phase 2: Core Implementation

- [x] 2.1 `compute_drill_compliance(design_df, actual_df, match_by='label', tolerances=None, group_by=None)` skeleton + empty guards → empty result + warnings
- [x] 2.2 Label match: inner join on `Pozo`; unmatched → `unmatched["design"]` / `unmatched["actual"]`
- [x] 2.3 Nearest fallback: `cKDTree(design[[X,Y]])` per actual; reject > 5.0 m → unmatched (never silent mis-pair)
- [x] 2.4 Auto-fallback: `match_by='label'` but design lacks `Pozo` → warning + nearest
- [x] 2.5 Compute 7 Δ: dX, dY, dZ signed, dIncl signed, dAz = `((az_a - az_d + 180) % 360) - 180`, dLen, dKg_pct = `abs(kg_a - kg_d) / max(kg_d, 1) * 100`
- [x] 2.6 `aggregates` = mean |Δ| per dim; `compliance_score` = fraction of holes where all 7 dimensions are within tolerance; `None` on empty
- [x] 2.7 `per_group` when `group_by` set: `n`, `mean_abs` × 7, `within_tol_pct` × 7 per group
- [x] 2.8 Tolerance override: caller dataclass replaces fields on `DRILL_COMPLIANCE`

## Phase 3: Testing

- [x] 3.1 test_label_match: shared `Pozo='H-1'` → per_hole row, `match_method='label'`, 7 Δ fields
- [x] 3.2 test_unmatched_label_drop: actual `Pozo` without design → `unmatched['actual']`
- [x] 3.3 test_nearest_match: actual (100,200) + design (101,199) → matched; > 5 m → unmatched
- [x] 3.4 test_auto_fallback: design lacks `Pozo` + `match_by='label'` → warning + nearest
- [x] 3.5 test_azimuth_wrap: `Az_d=179°, Az_a=181°` → `dAz=2°` (not 358°)
- [x] 3.6 test_graceful_empty: None design, empty actual, missing X/Y → empty + warning, no raise
- [x] 3.7 test_compliance_score: all in tol → 1.0; one hole failing any dimension → that hole is non-compliant
- [x] 3.8 test_per_group_malla: 30 holes `malla ∈ {M-1, M-2}` → 2 rows × (7 mean_abs + 7 within_tol_pct)
- [x] 3.9 test_tolerance_override: `DrillComplianceDefaults(dx_m=1.0)` → ΔX 1.0 m, rest defaults
- [x] 3.10 Extend `test_pipeline.py` with synthetic ENAEX + design → end-to-end `procesar_pozos → compute_drill_compliance`

## Phase 4: Integration & UI (AGENTS.md `ui/` off-limits)

- [x] 4.1 Add second `st.file_uploader` (CSV) for design in `ui/modulo_tronadura.py` below line 51
- [x] 4.2 On upload: `compute_drill_compliance(design_df, df_clean)` post `procesar_pozos`; absent → `st.info("Sin diseño cargado — omitiendo verificación")`
- [x] 4.3 Render `_render_drill_compliance_block`: Spanish expander + per_hole table + `st.metric("Cumplimiento", score)` + unmatched warnings
- [x] 4.4 Append entry to `openspec/changes/ACTIVE.md` per AGENTS.md
- [x] 4.5 Run `pytest tests/test_drill_compliance.py -v --tb=short` + `python test_pipeline.py` green

## Phase 5: Verification Gates

- [x] 5.1 `core/__init__.py` re-exports unchanged — no `drill_compliance` symbol (additive-only)
- [x] 5.2 `procesar_pozos`, `proyectar_pozos_en_seccion` signatures unchanged — legacy API intact
- [x] 5.3 `ui/modulo_tronadura.py` flagged: maintainer `ui/` off-limits → raise before apply
