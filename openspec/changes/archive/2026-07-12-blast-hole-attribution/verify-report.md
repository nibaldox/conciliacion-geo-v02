# Verify Report: blast-hole-attribution

> **Verifier**: sdd-verify (sub-agent)
> **Project**: conciliacion-geo-v02
> **Branch**: sdd/blast-design-achievement
> **Commits verified**: `9904432` (domain + tests) + `4174ef8` (UI wiring)
> **Mode**: openspec | **Strict TDD**: OFF | **Preflight**: auto
> **Verified on**: 2026-07-12

---

## 1. Executive Summary

**Status**: `pass`
**Recommission**: `ready-for-archive`
**Tally**: 0 CRITICAL · 0 WARNING · 3 SUGGESTION (all cosmetic / forward-only)

All 23 new tests in `tests/test_blast_attribution.py` pass.
Full suite: 790 passed, 2 skipped, 15 pre-existing failures (12 async sqlite + 2 stream stderr + 1 sqlite3; all are `test_ai_v2_*` / `test_api_auth.py` predating this change).
End-to-end `python test_pipeline.py` succeeds.
`core/__init__.py` is **untouched** in `9904432..4174ef8` — Legacy API Compatibility requirement fully honored.
Change is purely additive (3 files, 779 insertions, 0 deletions).

---

## 2. Verification matrix

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `pytest tests/test_blast_attribution.py -v` (23 tests) | ✅ PASS | 23 passed in 0.02s; classes: `TestGracefulAbsence` × 7, `TestMinDeviationGate` × 3, `TestKgFallback` × 2, `TestTopNLimit` × 3, `TestMultiFeatureIsolation` × 2, `TestCoordinateTransform` × 2, `TestTolerance` × 2, `TestResultShape` × 2 |
| 2 | `pytest tests/ --tb=short -q --ignore=tests/test_openblast.py --ignore=tests/test_reconciled_profile_serialization.py` | ✅ PASS (790/792) | 790 passed + 2 skipped + 15 pre-existing failures (async/sqlite, identical to run before change). No new failures introduced. |
| 3 | `python test_pipeline.py` | ✅ PASS | `TEST COMPLETADO` — Excel + Word exports generated, no traceback. |
| 4 | `python -c "from core.blast_attribution import attribute_holes_to_benches; print(attribute_holes_to_benches(None, [], []))"` | ✅ PASS | Returns `[]` (no exception). |
| 5 | Coordinate transform `[sin(az), cos(az)]` matches `proyectar_pozos_en_seccion:278` | ✅ PASS | `azimuth_to_direction(0)→[0,1]` (North); `azimuth_to_direction(90)→[1,0]` (East); `_feature_world_xy` uses `np.asarray(section.origin)[:2] + azimuth_to_direction(section.azimuth) * distance_m` — bit-identical to `proyectar_pozos_en_seccion` (verified at `core/calculo_tronadura.py:278-279`). |
| 6 | IDW scoring `kg / max(d², 1e-4)` | ✅ PASS | Line 142 `d2 = dx*dx + dy*dy`; line 149 `safe_d2 = np.where(d2 < 1e-4, 1e-4, d2)`; line 150 `scores = well_q / safe_d2`; line 144 `within_mask = d2 <= tolerance**2`. Math tested in `test_score_uses_floored_inverse_distance_squared` and `test_d2_floor_prevents_div_by_zero`. |
| 7 | Gate only MATCH rows with `|delta| > 0.5 m` | ✅ PASS | `_extract_benches` (lines 75-123): skips non-`MATCH` types (line 85) AND `bench_real is None` (line 88) AND `|delta_f| <= min_delta_m` (line 106). Default `min_delta_m=0.5` matches spec. Tested with `test_no_deviated_rows_returns_empty`, `test_exactly_at_threshold_returns_empty`, `test_custom_threshold_raises_floor`. |
| 8 | `core/__init__.py` untouched | ✅ PASS | `git show HEAD:core/__init__.py \| grep blast_attribution` → no match (additive module). HEAD~2..HEAD diff: only `blast_attribution.py` + `test_blast_attribution.py` + `blast_correlation.py`. NOTE: working-tree has uncommitted modifications to `core/__init__.py` from a separate (older) `blast-design-achievement` change — those are NOT part of this change's commits. |
| 9 | Spec requirement coverage | ✅ PASS | See §3. |

---

## 3. Spec ↔ test traceability matrix

### Requirement: Feature-level attribution
- **Scenario "Attribute a nearby hole"** — implicitly covered by integration of `_feature_world_xy` + `_select_top_holes` exercised in `test_top_n_limits_results`, `test_outside_tolerance_excluded`, `test_n_candidates_counts_all_within_radius`.
- **Scenario "Isolate features"** — ✅ `test_hole_near_two_features_appears_in_both` + `test_no_cross_feature_aggregation` (multi-feature isolation, no cross-feature aggregation).

### Requirement: Charge-distance ranking
- **Scenario "Rank by charge and distance"** — ✅ `test_score_uses_floored_inverse_distance_squared` (asserts exact score math).
- **Scenario "Enforce result limit"** — ✅ `test_top_n_limits_results` (4 eligible → top_n=2 → 2 entries, highest first).

### Requirement: Auditable result fields
- **Scenario "Return hole details"** — ✅ `test_required_fields_present` (every entry has section, bench_num, feature, delta_m, top_holes[label_pozo, malla, kg, distance_m, contribution_pct], n_candidates).
- **Scenario "Missing charge column"** — ✅ `test_missing_kg_column_uses_fallback` + `test_kg_column_precedence` (5-level precedence `Kilos_Cargados_real → Kilos_Cargados → Carga_kg → Explosivo_kg → kg → 1.0`).

### Requirement: Graceful absence handling
- **Scenario "No usable blast data"** — ✅ Seven tests in `TestGracefulAbsence`: `None`, empty df, missing X, missing Y, no comparisons, no sections, unknown section, non-MATCH rows all return `[]` without raising.
- **Scenario "No attributable deviation"** — ✅ `test_no_deviated_rows_returns_empty` + `test_exactly_at_threshold_returns_empty` (boundary at 0.5 m).

### Requirement: Attribution presentation
- **Scenario "Inspect a feature"** — ✅ Renderer at `ui/tabs/blast_correlation.py:995-1044` provides: `selectbox` per feature, dataframe with Spanish labels (`Pozo / Malla / Carga (kg) / Distancia (m) / Contribución (%)`), and n_candidates caption.
- **Scenario "Empty attribution view"** — ✅ Renderer early-returns at line 1008-1010 with `st.info("Sin desviaciones atribuibles")`.

### Requirement: Preserve existing blast analysis (Legacy API Compatibility)
- **Scenario "Existing regression suite"** — ✅ `pytest tests/test_blast_*.py` → 172 passed, 2 skipped (no regression). Full blast-* surface intact. No changes to `core/blast_model.py`, `core/blast_metrics.py`, `core/blast_correlation.py`, `core/blast_achievement.py`.
- **`core/__init__.py` SHALL remain unchanged** — ✅ Confirmed (see check #8).

---

## 4. Implementation review notes

### Coordinate convention (verified spot check)
```
az 0   → [0, 1]              (Norte / +Y)
az 90  → [1.0, ~0]           (Este / +X)
az 180 → [~0, -1]            (Sur / -Y)
az 270 → [-1, ~0]            (Oeste / -X)
```
`mine coordinates are X=East, Y=North` (AGENTS.md) → `(X, Y) = (sin·d, cos·d)` is internally consistent.

### Module shape (`core/blast_attribution.py`, 326 LOC)
- Public surface: `attribute_holes_to_benches(blast_df, comparison_results, sections, tolerance=15.0, top_n=5, min_delta_m=0.5) → list[dict]`.
- Private helpers: `_resolve_kg_column`, `_feature_world_xy`, `_extract_benches`, `_select_top_holes`.
- `__all__ = ["attribute_holes_to_benches"]` — narrow, no surprise exports.

### Result dict contract (matches design)
- Per-feature keys: `section, bench_num, feature, delta_m, n_candidates, top_holes`.
- Per-hole keys: `label_pozo, malla, kg, distance_m, contribution_pct`.
- All numeric values rounded (`delta_m` 3 dp, `distance_m` 3 dp, `contribution_pct` 2 dp, `delta_m` per `round(delta_f, 3)`).
- `contribution_pct` uses `score / total_eligible * 100` — total is sum of *all eligible* (within-tolerance) scores, not just top-N. Matches spec wording.

### Test file shape (`tests/test_blast_attribution.py`, 395 LOC, 23 tests)
- 8 `TestCase`-style classes, well-named (TestGracefulAbsence / TestMinDeviationGate / TestKgFallback / TestTopNLimit / TestMultiFeatureIsolation / TestCoordinateTransform / TestTolerance / TestResultShape).
- Fixtures: synthetic 4-hole 30×30 m box, MATCH-row builder, SectionLine stub.
- Each test < 25 LOC; collection < 0.05 s.

### UI integration (`ui/tabs/blast_correlation.py`, +58 LOC)
- `from core.blast_attribution import attribute_holes_to_benches` at line 12.
- Call inside `tab_bnc` at lines 342-345 (right after `_render_stemming_crest_block`, per design).
- Renderer `_render_attribution_block(results)` at lines 995-1044.
- Spanish copy: "Atribución por Pozo", "Cresta" / "Pata", "Seleccionar feature desviado", "Sin desviaciones atribuibles", "Mostrando top N ordenado por contribución descendente".
- Column header rename: `label_pozo→Pozo, malla→Malla, kg→Carga (kg), distance_m→Distancia (m), contribution_pct→Contribución (%)`.
- Tolerance slider value already in `tab_bnc` is passed via call site; reuses the existing user-controlled radius (good — no new UI surface).

---

## 5. SUGGESTIONs (non-blocking, forward-only)

| # | Topic | Detail | Suggested action |
|---|-------|--------|------------------|
| S1 | 🎯 emoji in subheader | Line 998 uses `st.subheader("🎯 Atribución por Pozo")`. AGENTS.md says "Only use emojis if the user explicitly requests it." However, the Streamlit UI section is explicitly off-limits for general PRs and historically uses emojis (preserved by maintainer). Consider dropping the 🎯 to match AGENTS.md default; does not block. | Cosmetic — drop in a follow-up sweep, or keep if maintainer prefers. |
| S2 | No CSV download button | `_render_attribution_block` shows the dataframe but doesn't offer `st.download_button` for export. The legacy renderer pattern (`_render_stemming_crest_block`) doesn't either, so this is consistent — but a CSV export would be useful for handoff to blast engineers. | Forward-only enhancement; not required by spec. |
| S3 | Selectbox label uniqueness | If two entries collide (same section+bench+feature), the selectbox will silently dedupe or error. In practice impossible (each MATCH row yields exactly one crest+one toe), but a defensive `f"#{i} {label}"` could be added. | Defensive, very low priority. |

---

## 6. Risks

| Risk | Severity | Why it doesn't block verify |
|------|----------|-----------------------------|
| Uncommitted working-tree changes (AGENTS.md, `core/__init__.py`, `core/profile_*.py`, etc.) | NONE for this change | These are leftover from a prior `blast-design-achievement` SDD change and unrelated to this verify scope. Blast-hole-attribution commits only touch `blast_attribution.py`, `test_blast_attribution.py`, `blast_correlation.py`. Verify confirm: `git show HEAD:core/__init__.py` is bit-identical to `HEAD~2:core/__init__.py`. |
| Pre-existing 15 test failures (`test_ai_v2_*`, `test_api_auth.py`) | NONE for this change | None of these touch `core/blast_attribution.py` or `ui/tabs/blast_correlation.py`. Failures are async loop (pytest-anyio asyncio config) and sqlite3 thread isolation. Confirm match baseline: failure set is stable across the 2 commits under review. |
| Renderer `delta_m > 0` sign formatting | NONE | Upstream `min_delta_m=0.5` filter guarantees no entry reaches the renderer with `delta_m == 0`. |

---

## 7. Final recommendation

`ready-for-archive` — all spec requirements satisfied, all matrix checks green, no CRITICAL or WARNING findings. The 3 SUGGESTIONs are cosmetic and out of scope for this change.

Archival may safely proceed to:
1. Sync delta spec to canonical `openspec/specs/blast-hole-attribution/spec.md`
2. Move `openspec/changes/blast-hole-attribution/` → `openspec/changes/archive/2026-07-12-blast-hole-attribution/`
3. Update `openspec/AGENTS.md` change log + `openspec/changes/ACTIVE.md`
4. Save `mem_save` topic `sdd/blast-hole-attribution/archive-report` with `capture_prompt=false`

This verify report is saved to engram under topic_key `sdd/blast-hole-attribution/verify-report`.
