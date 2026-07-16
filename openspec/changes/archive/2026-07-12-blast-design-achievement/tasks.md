# Tasks: blast-design-achievement

> Pure additive. Mirrors pasadura 1:1 + new scoring module. Single PR, 4 work-unit commits.

## Review Workload Forecast

Decision needed before apply: **No** (under 400-line budget; orchestrator asks per `ask-always`)
Chained PRs recommended: **No**
Chain strategy: **pending**
400-line budget risk: **Low**

Estimated ~386 changed lines (design § Changed-Lines Estimate). Single PR, 4 work-unit commits: (1) stemming fn + 4 tests, (2) achievement module + 4 tests, (3) UI wiring, (4) `ACTIVE.md` row.

## Phase 1: Core — stemming↔crest correlation

- [x] 1.1 Add `compute_stemming_crest_correlation(blast_df, comparisons, bench_height=15.0, taco_column=None)` to `core/blast_model.py` after line 329 (~75 LOC). Mirror pasadura 1:1 — same shape `{taco_per_bench, crest_per_bench, r, p_value, n_benches, interpretation}`, same guards, lazy `from scipy import stats`. Resolve taco via `first_present_column(blast_df, _TACO_CANDIDATES)` from `core/blast_metrics`. Floor: `(df["Z_collar"] - bench_height).round(0)`.
- [x] 1.2 Interpretation per spec: `r < -0.3` → "gases venting up"; `r > 0.3` → "energía baja / sobre-excavación de cresta"; else weak/null. Empty fallback: `n_benches=0`, `r=0.0`, `p_value=nan`, "Sin datos suficientes". **Accept**: `core/__init__.py` untouched.
- [x] 1.3 Create `tests/test_blast_model.py` with 4 tests mirroring `tests/test_blast_correlation.py:426-474`: basic (negative r, 4 floors), no_data, only_one_bench (n=1 → "2" in interp), missing_columns. ~85 LOC. **Accept**: `pytest tests/test_blast_model.py -v` → 4 passed.

## Phase 2: Core — design achievement score

- [x] 2.1 Create `core/blast_achievement.py` (~90 LOC). Constants `W_CREST=0.4`, `W_TOE=0.3`, `W_BERM=0.3`. `_row_credit(status)`: `STATUS_CUMPLE → 1.0`, `STATUS_FUERA → 0.5`, else `0.0`. Import statuses from `core.compliance_status`. Define `__all__`.
- [x] 2.2 Implement `compute_design_achievement_score(comparisons, malla_to_section=None, crest_tolerance_m=None, toe_tolerance_m=None)`. Derive `crest_status`/`toe_status` per row from `|delta|` vs tol (default `TOLERANCES.bench_height["pos"]` = 1.5 m). Berm: `berm_status == STATUS_CUMPLE`. Score = `0.4·crest + 0.3·toe + 0.3·berm`. Return `{global (int 0-100), breakdown, per_malla: dict|None, n_total, n_passing_crest/toe/berm}`. **Accept**: all-CUMPLE → `global==100`.
- [x] 2.3 Per-malla: when `malla_to_section: {malla: [sections]}` given, filter+score per group. Else `per_malla=None`. Empty/`None`/`{}` safe.
- [x] 2.4 Create `tests/test_blast_achievement.py` (4 tests, ~75 LOC): weights_sum_to_one, all_cumple_returns_100, fuera_partial_credit_0_5 (5+5 crest mix → `global≈70`), missing_malla_column_returns_none. **Accept**: `pytest tests/test_blast_achievement.py -v` → 4 passed.

## Phase 3: UI wiring (blast tab only)

- [x] 3.1 In `ui/tabs/blast_correlation.py` (imports lines 20-25), add `compute_stemming_crest_correlation` to blast_model import + `from core.blast_achievement import compute_design_achievement_score`. Append `_render_stemming_crest_block` after line 903 (~40 LOC): copy-with-replace of pasadura block (same `st.markdown("---")`, subheader, 3-col `st.metric`, warning/info) with gases/energía thresholds. Invoke at line 904 in `tab_bnc`. **Accept**: renders; no exception on empty `blast_df`.
- [x] 3.2 In `tab_mal`, build `malla_to_section` from `_compute_malla_correlation` join (lines 580-667), call `compute_design_achievement_score(df_comps_match, malla_to_section=...)`, attach `score_pct` to `df_malla_corr`. Append `'score_pct'` to `col_list_m` AFTER `energy_total_mj`; `display_map_m['score_pct'] = 'Logro Diseño (%)'`. `st.metric("Logro Diseño Global", f"{global}%")` above dataframe at line 357. **Accept**: column 0-100 visible; existing columns unchanged.

## Phase 4: Verification & bookkeeping

- [x] 4.1 `pytest tests/test_blast_model.py tests/test_blast_achievement.py tests/test_blast_correlation.py -v --tb=short`. **Accept**: 8 new + pre-existing pasadura/PF pass.
- [x] 4.2 `python test_pipeline.py`. **Accept**: end-to-end pipeline completes.
- [x] 4.3 Update `openspec/changes/ACTIVE.md`: advance Phase `proposal → tasks`, mark Tasks ✅.

## Flags

- **Stemming column**: `_TACO_CANDIDATES = ("Taco_m", "Taco", "Stemming")` at `core/blast_metrics.py:37`. `Taco_m` canonical post-enrich. Use `first_present_column`; do not hardcode.
- **Tolerance default**: `TOLERANCES.bench_height["pos"] = 1.5 m` per `core/config.py:27`. Override knobs keep tests deterministic.
- **Scope override**: `ui/tabs/blast_correlation.py` ONLY. `app.py` + other `ui/` off-limits. `core/__init__.py`: do NOT modify per AGENTS.md.